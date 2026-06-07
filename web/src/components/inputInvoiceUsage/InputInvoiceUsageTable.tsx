import { Info } from "lucide-react";
import type { MutableRefObject, ReactNode } from "react";

import type {
  InputInvoiceUsageDetailTarget,
  InputInvoiceUsageRow,
} from "../../features/inputInvoiceUsage/types";
import ExpandableCellText from "./ExpandableCellText";

type InputInvoiceUsageTableProps = {
  rows: InputInvoiceUsageRow[];
  page: number;
  pageSize: number;
  total: number;
  expandedCells: Set<string>;
  onToggleCellExpand: (rowId: string, cellId: string) => void;
  onOpenDetail: (target: InputInvoiceUsageDetailTarget) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
};

const PAGE_SIZE_OPTIONS = [20, 50, 100];

function displayInvoiceNo(row: InputInvoiceUsageRow) {
  const invoice = row.invoice;
  if (invoice.displayNo) {
    return invoice.displayNo;
  }
  if (invoice.digitalInvoiceNo) {
    return invoice.digitalInvoiceNo;
  }
  return [invoice.invoiceCode, invoice.invoiceNo].filter(Boolean).join(" ") || "-";
}

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value || "-";
  }
  return parsed.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function dateOnly(value: string) {
  if (!value) {
    return "日期为空";
  }
  return value.includes("T") ? value.split("T")[0] : value;
}

function classNames(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

function HeaderCell({
  label,
  align,
  separated,
  strongSeparated,
  emphasized,
}: {
  label: ReactNode;
  align?: "left" | "right" | "center";
  separated?: boolean;
  strongSeparated?: boolean;
  emphasized?: boolean;
}) {
  return (
    <th
      className={classNames(
        "input-invoice-usage-table-sub-header",
        align && `input-invoice-usage-table-sub-header--${align}`,
        separated && "input-invoice-usage-table-cell--separator",
        strongSeparated && "input-invoice-usage-table-cell--strong-separator",
        emphasized && "input-invoice-usage-table-cell--payment",
      )}
      scope="col"
    >
      <span className="input-invoice-usage-table-header-stack">{label}</span>
    </th>
  );
}

function EmptyCell() {
  return <span className="input-invoice-usage-empty-value">-</span>;
}

function Tag({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "warning" | "info" | "success";
  className?: string;
}) {
  return (
    <span className={classNames("input-invoice-usage-tag", `input-invoice-usage-tag--${tone}`, className)}>
      {children}
    </span>
  );
}

function DetailButton({
  label,
  children,
  onClick,
  iconOnly = false,
}: {
  label: string;
  children?: ReactNode;
  onClick: () => void;
  iconOnly?: boolean;
}) {
  return (
    <button
      aria-label={label}
      className={classNames("input-invoice-usage-table-action", iconOnly && "input-invoice-usage-table-action--icon")}
      onClick={onClick}
      title={label}
      type="button"
    >
      {iconOnly ? <Info aria-hidden="true" size={14} /> : children}
    </button>
  );
}

function displayedRange(page: number, pageSize: number, total: number) {
  if (total <= 0) {
    return "0-0 / 0";
  }
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const from = (currentPage - 1) * pageSize + 1;
  const to = Math.min(currentPage * pageSize, total);
  return `${from}-${to} / ${total}`;
}

export default function InputInvoiceUsageTable({
  rows,
  page,
  pageSize,
  total,
  expandedCells,
  onToggleCellExpand,
  onOpenDetail,
  onPageChange,
  onPageSizeChange,
  tableWrapRef,
}: InputInvoiceUsageTableProps) {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const canGoPrevious = page > 1;
  const canGoNext = page < totalPages;

  return (
    <div className="input-invoice-usage-table-frame">
      <div ref={tableWrapRef} className="input-invoice-usage-table-shell">
        <table aria-label="进项发票使用情况表" className="input-invoice-usage-table">
          <colgroup>
            <col className="input-invoice-usage-col-invoice-no" />
            <col className="input-invoice-usage-col-seller" />
            <col className="input-invoice-usage-col-invoice-amount" />
            <col className="input-invoice-usage-col-business" />
            <col className="input-invoice-usage-col-payment" />
            <col className="input-invoice-usage-col-oa-applicant" />
            <col className="input-invoice-usage-col-oa-project" />
            <col className="input-invoice-usage-col-bank-name" />
            <col className="input-invoice-usage-col-bank-amount" />
            <col className="input-invoice-usage-col-bank-remark" />
          </colgroup>
          <thead>
            <tr>
              <th className="input-invoice-usage-table-group-header input-invoice-usage-table-group-header--invoice" colSpan={4} scope="colgroup">
                进项发票
              </th>
              <th className="input-invoice-usage-table-group-header input-invoice-usage-table-group-header--payment input-invoice-usage-table-cell--strong-separator" colSpan={1} scope="colgroup">
                支付状态
              </th>
              <th className="input-invoice-usage-table-group-header input-invoice-usage-table-group-header--oa input-invoice-usage-table-cell--strong-separator" colSpan={2} scope="colgroup">
                OA
              </th>
              <th className="input-invoice-usage-table-group-header input-invoice-usage-table-group-header--bank input-invoice-usage-table-cell--strong-separator" colSpan={3} scope="colgroup">
                流水
              </th>
            </tr>
            <tr>
              <HeaderCell label="发票号码" />
              <HeaderCell label="销方" separated />
              <HeaderCell
                align="right"
                label={(
                  <>
                    <span>价税合计</span>
                    <span>不含税/税率税额</span>
                  </>
                )}
                separated
              />
              <HeaderCell label="货物或应税劳务名称" separated />
              <HeaderCell label="支付状态" strongSeparated emphasized />
              <HeaderCell label="OA申请人" strongSeparated />
              <HeaderCell label="项目名称" separated />
              <HeaderCell label="对方户名" strongSeparated />
              <HeaderCell label="金额" align="right" separated />
              <HeaderCell label="摘要/备注" separated />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="input-invoice-usage-table-state-cell" colSpan={10}>
                  当前条件下没有进项发票使用记录。
                </td>
              </tr>
            ) : rows.map((row) => {
              const invoiceNo = displayInvoiceNo(row);
              const invoiceCellExpanded = expandedCells.has(`${row.id}:invoice-business`);
              const paymentCellExpanded = expandedCells.has(`${row.id}:payment-status`);
              const projectCellExpanded = expandedCells.has(`${row.id}:oa-project`);
              const bankNameCellExpanded = expandedCells.has(`${row.id}:bank-name`);
              const bankRemarkCellExpanded = expandedCells.has(`${row.id}:bank-remark`);
              const oa = row.oa.primary;
              const bank = row.bank.primary;

              return (
                <tr className="input-invoice-usage-table-row" key={row.id}>
                  <td className="input-invoice-usage-table-cell">
                    <div className="input-invoice-usage-inline-row">
                      <span className="input-invoice-usage-cell-primary" title={invoiceNo}>{invoiceNo}</span>
                      <DetailButton
                        iconOnly
                        label={`查看发票 ${invoiceNo} 详情`}
                        onClick={() => onOpenDetail({ kind: "invoice", id: row.invoice.id, rowId: row.id })}
                      />
                    </div>
                    <div className="input-invoice-usage-tag-row">
                      <Tag>{dateOnly(row.invoice.issueDate)}</Tag>
                    </div>
                  </td>
                  <td className="input-invoice-usage-table-cell input-invoice-usage-table-cell--separator">
                    <div className="input-invoice-usage-cell-primary">{row.invoice.sellerName || "-"}</div>
                    <div className="input-invoice-usage-cell-secondary">{row.invoice.sellerTaxNo || "-"}</div>
                  </td>
                  <td className="input-invoice-usage-table-cell input-invoice-usage-table-cell--amount input-invoice-usage-table-cell--separator">
                    <div className="input-invoice-usage-money-primary">{formatMoney(row.invoice.totalWithTax)}</div>
                    <div className="input-invoice-usage-cell-secondary">
                      {`${formatMoney(row.invoice.amountWithoutTax)} ${row.invoice.taxRate || "-"} (${formatMoney(row.invoice.taxAmount)})`}
                    </div>
                  </td>
                  <td className="input-invoice-usage-table-cell input-invoice-usage-table-cell--separator">
                    <ExpandableCellText
                      text={row.invoice.taxableItemName}
                      expanded={invoiceCellExpanded}
                      onToggle={() => onToggleCellExpand(row.id, "invoice-business")}
                    />
                  </td>
                  <td className="input-invoice-usage-table-cell input-invoice-usage-table-cell--payment input-invoice-usage-table-cell--strong-separator input-invoice-usage-payment-cell">
                    <Tag tone="warning">{row.paymentStatus.label || "待处理"}</Tag>
                    <div className="input-invoice-usage-cell-block">
                      <ExpandableCellText
                        text={row.paymentStatus.reason}
                        expanded={paymentCellExpanded}
                        onToggle={() => onToggleCellExpand(row.id, "payment-status")}
                        threshold={22}
                      />
                    </div>
                  </td>
                  <td className="input-invoice-usage-table-cell input-invoice-usage-table-cell--strong-separator">
                    {oa ? (
                      <>
                        <div className="input-invoice-usage-cell-primary">{oa.applicant || "-"}</div>
                        <div className="input-invoice-usage-tag-row">
                          <Tag>{oa.applicationType || "类型为空"}</Tag>
                          {oa.detailAvailable ? (
                            <DetailButton
                              label={`查看OA ${oa.applicant || oa.id} 详情`}
                              onClick={() => onOpenDetail({ kind: "oa", id: oa.id, rowId: row.id })}
                            >
                              详情
                            </DetailButton>
                          ) : null}
                        </div>
                      </>
                    ) : <EmptyCell />}
                  </td>
                  <td className="input-invoice-usage-table-cell input-invoice-usage-table-cell--separator">
                    {oa ? (
                      <ExpandableCellText
                        text={oa.projectName}
                        expanded={projectCellExpanded}
                        onToggle={() => onToggleCellExpand(row.id, "oa-project")}
                      />
                    ) : <EmptyCell />}
                  </td>
                  <td className="input-invoice-usage-table-cell input-invoice-usage-table-cell--strong-separator">
                    {bank ? (
                      <>
                        <ExpandableCellText
                          text={bank.counterpartyName}
                          expanded={bankNameCellExpanded}
                          onToggle={() => onToggleCellExpand(row.id, "bank-name")}
                        />
                        <div className="input-invoice-usage-tag-row">
                          <Tag>{bank.tradeTime || "交易日期为空"}</Tag>
                          {bank.detailAvailable ? (
                            <DetailButton
                              label={`查看流水 ${bank.counterpartyName || bank.id} 详情`}
                              onClick={() => onOpenDetail({ kind: "bank", id: bank.id, rowId: row.id })}
                            >
                              详情
                            </DetailButton>
                          ) : null}
                        </div>
                      </>
                    ) : <EmptyCell />}
                  </td>
                  <td className="input-invoice-usage-table-cell input-invoice-usage-table-cell--amount input-invoice-usage-table-cell--separator">
                    {bank ? (
                      <>
                        <div className="input-invoice-usage-money-primary">{formatMoney(bank.amount)}</div>
                        <Tag className="input-invoice-usage-bank-tag">
                          {`${bank.directionLabel || "收/支"} ${bank.bankName || "银行"} ${bank.accountLast4 || "----"}`}
                        </Tag>
                      </>
                    ) : <EmptyCell />}
                  </td>
                  <td className="input-invoice-usage-table-cell input-invoice-usage-table-cell--separator">
                    {bank ? (
                      <>
                        <div className="input-invoice-usage-cell-primary">{bank.summary || "-"}</div>
                        <ExpandableCellText
                          text={bank.remark}
                          expanded={bankRemarkCellExpanded}
                          onToggle={() => onToggleCellExpand(row.id, "bank-remark")}
                        />
                      </>
                    ) : <EmptyCell />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="input-invoice-usage-pagination">
        <label className="input-invoice-usage-pagination-size">
          <span>每页行数</span>
          <select
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </label>
        <span className="input-invoice-usage-pagination-range">{displayedRange(page, pageSize, total)}</span>
        <div className="input-invoice-usage-pagination-actions">
          <button disabled={!canGoPrevious} onClick={() => onPageChange(page - 1)} type="button">
            上一页
          </button>
          <button disabled={!canGoNext} onClick={() => onPageChange(page + 1)} type="button">
            下一页
          </button>
        </div>
      </div>
    </div>
  );
}

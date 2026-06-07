import { ArrowUpDown, Info } from "lucide-react";
import type { MutableRefObject, ReactNode } from "react";

import {
  EmptyValue,
  FinanceDirectionTag,
  FinanceStatusTag,
  type FinanceTone,
} from "../common/FinanceTable";
import InputInvoiceUsageFilterMenu from "../inputInvoiceUsage/InputInvoiceUsageFilterMenu";
import type { InputInvoiceUsageFilterValue } from "../inputInvoiceUsage/InputInvoiceUsageFilterMenu";
import type {
  OaPendingPaymentDetailTarget,
  OaPendingPaymentFieldConfig,
  OaPendingPaymentFilter,
  OaPendingPaymentFilterOption,
  OaPendingPaymentRow,
  OaPendingPaymentSortDirection,
} from "../../features/oaPendingPayments/types";

type OaPendingPaymentsTableProps = {
  rows: OaPendingPaymentRow[];
  page: number;
  pageSize: number;
  total: number;
  filterConfigs: OaPendingPaymentFieldConfig[];
  filterOptions: Record<string, OaPendingPaymentFilterOption[]>;
  filters: OaPendingPaymentFilter[];
  onFilterApply: (filter: { field: string; operator: string; value?: string | null; values?: string[] }) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OaPendingPaymentSortDirection) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onOpenDetail: (target: OaPendingPaymentDetailTarget) => void;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
};

type OaPendingPaymentColumn = {
  id: string;
  label: string;
  align?: "left" | "right";
  field?: string;
  filterable?: boolean;
  sortable?: boolean;
  group: "oa" | "status" | "bank" | "invoice";
};

const columns: OaPendingPaymentColumn[] = [
  { id: "oaApplicant", label: "OA申请人", field: "oa_applicant", filterable: true, group: "oa" },
  { id: "projectName", label: "项目名称", group: "oa" },
  { id: "oaAmount", label: "金额", align: "right", group: "oa" },
  { id: "paymentStatus", label: "支付状态", group: "status" },
  { id: "bankCounterparty", label: "对方户名/交易时间", field: "bank_trade_time", sortable: true, group: "bank" },
  { id: "bankAmountAccount", label: "金额/账户", align: "right", group: "bank" },
  { id: "bankSummaryRemark", label: "摘要/备注", group: "bank" },
  { id: "invoiceNoParty", label: "发票号码/发票方", group: "invoice" },
  { id: "invoiceDate", label: "日期", group: "invoice" },
  { id: "totalWithTax", label: "价税合计", align: "right", group: "invoice" },
];

function cx(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

export default function OaPendingPaymentsTable({
  rows,
  page,
  pageSize,
  total,
  filterConfigs,
  filterOptions,
  filters,
  onFilterApply,
  onFilterClear,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  onOpenDetail,
  tableWrapRef,
}: OaPendingPaymentsTableProps) {
  const configsByField = new Map(filterConfigs.map((config) => [config.field, config]));

  return (
    <div className="oa-pending-payments-table-frame">
      <div ref={tableWrapRef} className="oa-pending-payments-table-shell" data-testid="oa-pending-payments-table-shell">
        <table aria-label="OA待付款核对表格" className="oa-pending-payments-table">
          <colgroup>
            {columns.map((column) => (
              <col className={`oa-pending-payments-col-${column.id}`} key={column.id} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <GroupHeader group="oa" label="OA情况" span={3} />
              <GroupHeader group="status" label="支付状态" span={1} />
              <GroupHeader group="bank" label="支出流水" span={3} />
              <GroupHeader group="invoice" label="发票情况" span={3} />
            </tr>
            <tr>
              {columns.map((column) => {
                const field = column.field;
                const config = field ? configsByField.get(field) : undefined;
                const currentFilter = field
                  ? (filters.find((filter) => filter.field === field) as InputInvoiceUsageFilterValue | undefined)
                  : undefined;
                return (
                  <th
                    className={cx(
                      "oa-pending-payments-table-sub-header",
                      `oa-pending-payments-table-sub-header--${column.group}`,
                      column.align === "right" && "oa-pending-payments-table-cell--amount",
                      ["status", "bank", "invoice"].includes(column.group) && firstColumnInGroup(column.id) && "oa-pending-payments-table-cell--left-border",
                    )}
                    key={column.id}
                    scope="col"
                  >
                    {column.filterable && config ? (
                      <InputInvoiceUsageFilterMenu
                        currentFilter={currentFilter}
                        fieldConfig={config}
                        onApply={onFilterApply}
                        onClear={onFilterClear}
                        onSort={(direction) => field && onSortChange(field, direction)}
                        options={field ? filterOptions[field] ?? [] : []}
                      />
                    ) : column.sortable && field ? (
                      <SortButton
                        label={column.label}
                        sortLabel={column.id === "bankCounterparty" ? "交易时间" : column.label}
                        onClick={() => onSortChange(field)}
                      />
                    ) : (
                      <span>{column.label}</span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="oa-pending-payments-table-state-cell" colSpan={columns.length}>
                  暂无 OA 待付款核对数据
                </td>
              </tr>
            ) : rows.map((row) => (
              <tr className="oa-pending-payments-table-row" key={row.id}>
                <td className="oa-pending-payments-table-cell" data-column-role="identity">
                  <span className="oa-pending-payments-inline-row">
                    <TextLine strong value={row.oa.applicantName} />
                    <DetailButton
                      disabled={!row.oa.detailAvailable}
                      label={`查看 OA ${row.oa.applicantName} 详情`}
                      onClick={() => onOpenDetail({ kind: "oa", id: row.oa.id })}
                    />
                  </span>
                  <span className="oa-pending-payments-tag-row">
                    <TableTag>{row.oa.applicationType || "类型为空"}</TableTag>
                  </span>
                </td>
                <td className="oa-pending-payments-table-cell" data-column-role="description">
                  <TextLine value={row.oa.projectName} />
                </td>
                <td className="oa-pending-payments-table-cell oa-pending-payments-table-cell--amount" data-column-role="amount">
                  <TextLine numeric strong value={row.oa.amount} />
                </td>
                <td
                  className="oa-pending-payments-table-cell oa-pending-payments-table-cell--status oa-pending-payments-table-cell--left-border oa-pending-payment-status-cell"
                  data-column-role="status"
                >
                  <FinanceStatusTag tone={statusTone(row.paymentStatus.severity)}>
                    {row.paymentStatus.label}
                  </FinanceStatusTag>
                </td>
                <td className="oa-pending-payments-table-cell oa-pending-payments-table-cell--left-border" data-column-role="identity">
                  <TextLine strong value={row.bankTransaction.counterpartyName} />
                  <span className="oa-pending-payments-tag-row">
                    <TableTag>{row.bankTransaction.tradeTime || "交易时间为空"}</TableTag>
                  </span>
                </td>
                <td className="oa-pending-payments-table-cell oa-pending-payments-table-cell--amount" data-column-role="amount">
                  <span className="oa-pending-payments-amount-detail-row">
                    <TextLine numeric strong value={bankAmount(row)} />
                    <FinanceDirectionTag direction={row.bankTransaction.directionLabel || "支出"}>
                      {row.bankTransaction.directionLabel || "支出"}
                    </FinanceDirectionTag>
                    <DetailButton
                      disabled={!bankDetailTarget(row)}
                      label={bankDetailLabel(row)}
                      onClick={() => {
                        const target = bankDetailTarget(row);
                        if (target) {
                          onOpenDetail(target);
                        }
                      }}
                    />
                  </span>
                  <span className="oa-pending-payments-tag-row oa-pending-payments-tag-row--right">
                    <TableTag>{bankAccountLabel(row)}</TableTag>
                  </span>
                </td>
                <td className="oa-pending-payments-table-cell" data-column-role="description">
                  <MultiLineValue value={combinedBankSummaryRemark(row)} />
                </td>
                <td className="oa-pending-payments-table-cell oa-pending-payments-table-cell--left-border" data-column-role="identity">
                  <span className="oa-pending-payments-inline-row">
                    <TextLine strong value={row.invoice.digitalInvoiceNo} />
                    <DetailButton
                      disabled={!invoiceDetailTarget(row)}
                      label={invoiceDetailLabel(row)}
                      onClick={() => {
                        const target = invoiceDetailTarget(row);
                        if (target) {
                          onOpenDetail(target);
                        }
                      }}
                    />
                  </span>
                  <span className="oa-pending-payments-cell-caption">进项发票方名称</span>
                  <TextLine value={row.invoice.sellerName} />
                </td>
                <td className="oa-pending-payments-table-cell" data-column-role="date">
                  <TextLine value={row.invoice.invoiceDate} />
                </td>
                <td className="oa-pending-payments-table-cell oa-pending-payments-table-cell--amount" data-column-role="amount">
                  <TextLine numeric strong value={row.invoice.totalWithTax} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <PaginationControls
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
        page={page}
        pageSize={pageSize}
        total={total}
      />
    </div>
  );
}

function GroupHeader({ label, span, group }: { label: string; span: number; group: "oa" | "status" | "bank" | "invoice" }) {
  return (
    <th
      className={cx(
        "oa-pending-payments-table-group-header",
        `oa-pending-payments-table-group-header--${group}`,
        group !== "oa" && "oa-pending-payments-table-cell--left-border",
      )}
      colSpan={span}
      scope="colgroup"
    >
      {label}
    </th>
  );
}

function SortButton({ label, sortLabel, onClick }: { label: string; sortLabel: string; onClick: () => void }) {
  return (
    <button
      aria-label={`${sortLabel} 排序`}
      className="oa-pending-payments-sort-button"
      onClick={onClick}
      type="button"
    >
      <ArrowUpDown aria-hidden="true" size={14} strokeWidth={2.3} />
      <span>{label}</span>
    </button>
  );
}

function TextLine({
  value,
  strong = false,
  numeric = false,
}: {
  value: string | number | null | undefined;
  strong?: boolean;
  numeric?: boolean;
}) {
  const text = value == null || value === "" ? "-" : String(value);
  if (text === "-") {
    return <EmptyValue />;
  }
  return (
    <span
      className={cx(
        "oa-pending-payments-table-text",
        strong && "oa-pending-payments-table-text--strong",
        numeric && "oa-pending-payments-table-text--numeric",
      )}
      title={text}
    >
      {text}
    </span>
  );
}

function MultiLineValue({ value }: { value: string }) {
  const text = value || "-";
  if (text === "-") {
    return <EmptyValue />;
  }
  return (
    <span className="oa-pending-payments-table-multiline" title={text}>
      {text}
    </span>
  );
}

function TableTag({ children }: { children: ReactNode }) {
  return <span className="oa-pending-payments-table-tag">{children}</span>;
}

function DetailButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      className="oa-pending-payments-detail-button"
      disabled={disabled}
      onClick={onClick}
      title={label}
      type="button"
    >
      <Info aria-hidden="true" size={14} strokeWidth={2.3} />
    </button>
  );
}

function PaginationControls({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  return (
    <div className="oa-pending-payments-pagination">
      <label className="oa-pending-payments-pagination-size">
        <span>每页</span>
        <select
          aria-label="每页"
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
          value={pageSize}
        >
          {[20, 50, 100].map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </label>
      <span className="oa-pending-payments-pagination-range">{displayedRange(currentPage, pageSize, total)}</span>
      <span className="oa-pending-payments-pagination-actions">
        <button disabled={currentPage <= 1} onClick={() => onPageChange(currentPage - 1)} type="button">上一页</button>
        <button disabled={currentPage >= totalPages} onClick={() => onPageChange(currentPage + 1)} type="button">下一页</button>
      </span>
    </div>
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

function firstColumnInGroup(columnId: string) {
  return columnId === "paymentStatus" || columnId === "bankCounterparty" || columnId === "invoiceNoParty";
}

function bankAmount(row: OaPendingPaymentRow): string {
  return row.bankTransaction.amount || row.bankTransaction.paidTotal || row.bankTransaction.debitAmount || row.bankTransaction.creditAmount || "";
}

function bankAccountLabel(row: OaPendingPaymentRow): string {
  const bankName = row.bankTransaction.bankName || "银行";
  const last4 = row.bankTransaction.accountLast4 || accountLast4(row.bankTransaction.accountNo);
  return [bankName, last4].filter(Boolean).join(" ") || "-";
}

function accountLast4(value: string | undefined): string {
  const text = String(value || "").trim();
  return text.length >= 4 ? text.slice(-4) : "";
}

function combinedBankSummaryRemark(row: OaPendingPaymentRow): string {
  const summaries = row.bankTransaction.summaries?.length
    ? row.bankTransaction.summaries
    : [{
      summary: row.bankTransaction.summary,
      remark: row.bankTransaction.remark,
    }];
  const seen = new Set<string>();
  const lines: string[] = [];
  summaries.forEach((summary) => {
    [summary.summary, summary.remark].forEach((part) => {
      const text = String(part || "").trim();
      if (!text || seen.has(text)) {
        return;
      }
      seen.add(text);
      lines.push(text);
    });
  });
  return lines.join("\n");
}

function bankDetailTarget(row: OaPendingPaymentRow): OaPendingPaymentDetailTarget | null {
  if (row.bankTransaction.detailMode === "single" && row.bankTransaction.primaryBankTransactionId) {
    return { kind: "bank", id: row.bankTransaction.primaryBankTransactionId };
  }
  if (row.bankTransaction.detailMode === "list") {
    return { kind: "relationList", id: row.id, rowId: row.id, relationKind: "bank" };
  }
  return null;
}

function invoiceDetailTarget(row: OaPendingPaymentRow): OaPendingPaymentDetailTarget | null {
  if (row.invoice.detailMode === "single" && row.invoice.primaryInvoiceId) {
    return { kind: "invoice", id: row.invoice.primaryInvoiceId };
  }
  if (row.invoice.detailMode === "list") {
    return { kind: "relationList", id: row.id, rowId: row.id, relationKind: "invoice" };
  }
  return null;
}

function bankDetailLabel(row: OaPendingPaymentRow): string {
  const applicant = row.oa.applicantName || "该OA";
  if (row.bankTransaction.detailMode === "list") {
    return `查看${applicant}关联流水 ${row.bankTransaction.relationCount} 条`;
  }
  return `查看流水 ${applicant} 详情`;
}

function invoiceDetailLabel(row: OaPendingPaymentRow): string {
  const applicant = row.oa.applicantName || "该OA";
  if (row.invoice.detailMode === "list") {
    return `查看${applicant}关联发票 ${row.invoice.relationCount} 张`;
  }
  return `查看发票 ${applicant} 详情`;
}

function statusTone(severity: string | undefined): FinanceTone {
  if (severity === "success") {
    return "success";
  }
  if (severity === "error") {
    return "danger";
  }
  if (severity === "warning") {
    return "warning";
  }
  return "neutral";
}

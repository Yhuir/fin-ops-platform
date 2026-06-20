import { ArrowUpDown, Info } from "lucide-react";
import type { MutableRefObject, ReactNode } from "react";

import type {
  OutputInvoiceCollectionDetailTarget,
  OutputInvoiceCollectionFilter,
  OutputInvoiceCollectionFilterFieldConfig,
  OutputInvoiceCollectionFilterOption,
  OutputInvoiceCollectionRow,
  OutputInvoiceCollectionSortDirection,
  OutputInvoiceCollectionWorkflow,
} from "../../features/outputInvoiceCollections/types";
import ExpandableCellText from "./ExpandableCellText";
import OutputInvoiceCollectionFilterMenu, { type OutputInvoiceCollectionFilterValue } from "./OutputInvoiceCollectionFilterMenu";

type OutputInvoiceCollectionsTableProps = {
  rows: OutputInvoiceCollectionRow[];
  page: number;
  pageSize: number;
  total: number;
  sortField: string;
  sortDirection: OutputInvoiceCollectionSortDirection | "";
  filters: OutputInvoiceCollectionFilter[];
  filterConfigs: OutputInvoiceCollectionFilterFieldConfig[];
  filterOptions: Record<string, OutputInvoiceCollectionFilterOption[]>;
  canMutateData: boolean;
  expandedCells: Set<string>;
  onToggleCellExpand: (rowId: string, cellId: string) => void;
  onOpenDetail: (target: OutputInvoiceCollectionDetailTarget) => void;
  onOpenWorkflow: (target: NonNullable<OutputInvoiceCollectionWorkflow>) => void;
  onFilterApply: (filter: OutputInvoiceCollectionFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OutputInvoiceCollectionSortDirection) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  emptyStateMessage?: string;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
};

type OutputInvoiceCollectionColumn = {
  id: string;
  label: string;
  subLabel?: string;
  align?: "left" | "right" | "center";
  field?: string;
  extraFilters?: Array<{ field: string; label: string }>;
  group: "invoice" | "status" | "bank" | "receipt";
};

const columns: OutputInvoiceCollectionColumn[] = [
  { id: "invoiceNo", label: "发票号码", field: "invoice_no", extraFilters: [{ field: "invoice_date", label: "开票日期" }], group: "invoice" },
  { id: "buyer", label: "购方", field: "buyer_name", group: "invoice" },
  { id: "totalWithTax", label: "价税合计", subLabel: "税额/税率", field: "total_with_tax", align: "right", group: "invoice" },
  { id: "business", label: "业务/货物劳务", field: "taxable_item_name", group: "invoice" },
  { id: "collectionStatus", label: "收款状态", field: "collection_status", group: "status" },
  { id: "bankCounterparty", label: "付款方/日期", field: "bank_counterparty_name", group: "bank" },
  { id: "bankAmount", label: "收款金额", field: "bank_amount", align: "right", group: "bank" },
  { id: "bankSummary", label: "摘要", field: "bank_summary", group: "bank" },
  { id: "receiptStatus", label: "收据情况", field: "receipt_status", group: "receipt" },
];

const defaultFilterConfigs: Record<string, OutputInvoiceCollectionFilterFieldConfig> = {
  invoice_no: { field: "invoice_no", label: "发票号码", mode: "text", sortable: true, operators: ["contains", "equals"] },
  invoice_date: { field: "invoice_date", label: "开票日期", mode: "date", sortable: true, operators: ["between", "equals"] },
  buyer_name: { field: "buyer_name", label: "购方", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  total_with_tax: { field: "total_with_tax", label: "价税合计", mode: "money", sortable: true, operators: ["between", "equals"] },
  tax_amount: { field: "tax_amount", label: "税额/税率", mode: "money", sortable: true, operators: ["between", "equals"] },
  taxable_item_name: { field: "taxable_item_name", label: "业务/货物劳务", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  collection_status: { field: "collection_status", label: "收款状态", mode: "enum_multi", sortable: true, operators: ["in"] },
  bank_counterparty_name: { field: "bank_counterparty_name", label: "付款方/日期", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  bank_amount: { field: "bank_amount", label: "收款金额", mode: "money", sortable: true, operators: ["between", "equals"] },
  bank_summary: { field: "bank_summary", label: "摘要", mode: "text", sortable: true, operators: ["contains"] },
  receipt_status: { field: "receipt_status", label: "收据情况", mode: "enum_multi", sortable: true, operators: ["in"] },
};

function cx(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

export default function OutputInvoiceCollectionsTable({
  rows,
  page,
  pageSize,
  total,
  sortField,
  sortDirection,
  filters,
  filterConfigs,
  filterOptions,
  canMutateData,
  expandedCells,
  onToggleCellExpand,
  onOpenDetail,
  onOpenWorkflow,
  onFilterApply,
  onFilterClear,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  emptyStateMessage = "当前条件下没有销项发票收款记录。",
  tableWrapRef,
}: OutputInvoiceCollectionsTableProps) {
  const configsByField = new Map(filterConfigs.map((config) => [config.field, config]));
  const activeSortLabel = sortField && sortDirection ? `${sortField} ${sortDirection}` : undefined;

  const fieldConfig = (field: string) => configsByField.get(field) ?? defaultFilterConfigs[field];
  const currentFilter = (field: string) => filters.find((filter) => filter.field === field);

  return (
    <div className="output-invoice-collections-table-frame">
      <div ref={tableWrapRef} className="output-invoice-collections-table-shell" data-testid="output-invoice-collections-table-shell">
        <table aria-label="销项发票收款情况表" className="output-invoice-collections-table">
          <colgroup>
            {columns.map((column) => (
              <col className={`output-invoice-collections-col-${column.id}`} key={column.id} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <GroupHeader group="invoice" label="销项发票" span={4} />
              <GroupHeader group="status" label="收款状态" span={1} />
              <GroupHeader group="bank" label="收入流水" span={3} />
              <GroupHeader group="receipt" label="收据" span={1} />
            </tr>
            <tr aria-label={activeSortLabel}>
              {columns.map((column) => (
                <th
                  className={cx(
                    "output-invoice-collections-table-sub-header",
                    `output-invoice-collections-table-sub-header--${column.group}`,
                    column.align === "right" && "output-invoice-collections-table-cell--amount",
                    column.align === "center" && "output-invoice-collections-table-cell--center",
                    firstColumnInGroup(column.id) && "output-invoice-collections-table-cell--left-border",
                  )}
                  key={column.id}
                  scope="col"
                >
                  <span className={cx(
                    "output-invoice-collections-table-header-stack",
                    column.align === "right" && "output-invoice-collections-table-header-stack--right",
                  )}>
                    {column.field && fieldConfig(column.field) ? (
                      <OutputInvoiceCollectionFilterMenu
                        currentFilter={currentFilter(column.field) as OutputInvoiceCollectionFilterValue | null}
                        fieldConfig={{
                          field: fieldConfig(column.field).field,
                          label: column.label,
                          mode: fieldConfig(column.field).mode,
                          sortable: fieldConfig(column.field).sortable,
                          operators: fieldConfig(column.field).operators,
                        }}
                        onApply={onFilterApply}
                        onClear={onFilterClear}
                        onSort={(direction) => column.field && onSortChange(column.field, direction)}
                        options={filterOptions[column.field] ?? []}
                      />
                    ) : <span>{column.label}</span>}
                    {column.field && fieldConfig(column.field)?.sortable !== false ? (
                      <SortButton
                        label={column.label}
                        onClick={() => {
                          if (column.field) {
                            onSortChange(column.field);
                          }
                        }}
                      />
                    ) : null}
                    {column.extraFilters?.map((extraFilter) => {
                      const extraConfig = fieldConfig(extraFilter.field);
                      return extraConfig ? (
                        <OutputInvoiceCollectionFilterMenu
                          key={extraFilter.field}
                          currentFilter={currentFilter(extraFilter.field) as OutputInvoiceCollectionFilterValue | null}
                          fieldConfig={{
                            field: extraConfig.field,
                            label: extraFilter.label,
                            mode: extraConfig.mode,
                            sortable: extraConfig.sortable,
                            operators: extraConfig.operators,
                          }}
                          onApply={onFilterApply}
                          onClear={onFilterClear}
                          onSort={(direction) => onSortChange(extraFilter.field, direction)}
                          options={filterOptions[extraFilter.field] ?? []}
                        />
                      ) : null;
                    })}
                    {column.subLabel ? (
                      <span className="output-invoice-collections-table-header-sub-label">{column.subLabel}</span>
                    ) : null}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="output-invoice-collections-table-state-cell" colSpan={columns.length}>
                  {emptyStateMessage}
                </td>
              </tr>
            ) : rows.map((row) => (
              <OutputInvoiceCollectionDataRow
                key={row.id}
                canMutateData={canMutateData}
                expandedCells={expandedCells}
                onOpenDetail={onOpenDetail}
                onOpenWorkflow={onOpenWorkflow}
                onToggleCellExpand={onToggleCellExpand}
                row={row}
              />
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

function OutputInvoiceCollectionDataRow({
  row,
  canMutateData,
  expandedCells,
  onToggleCellExpand,
  onOpenDetail,
  onOpenWorkflow,
}: {
  row: OutputInvoiceCollectionRow;
  canMutateData: boolean;
  expandedCells: Set<string>;
  onToggleCellExpand: (rowId: string, cellId: string) => void;
  onOpenDetail: (target: OutputInvoiceCollectionDetailTarget) => void;
  onOpenWorkflow: (target: NonNullable<OutputInvoiceCollectionWorkflow>) => void;
}) {
  const invoiceNo = displayInvoiceNo(row);
  const invoiceCellExpanded = expandedCells.has(`${row.id}:invoice-business`);
  const bankSummaryCellExpanded = expandedCells.has(`${row.id}:bank-summary`);
  const bank = row.bank.primary;
  const bankAccountLabel = bank ? accountLabel(bank.bankName, bank.accountLast4) : "";

  return (
    <tr className="output-invoice-collections-table-row">
      <td className="output-invoice-collections-table-cell" data-column-role="identity">
        <span className="output-invoice-collections-inline-row">
          <TextLine strong value={invoiceNo} />
          <ActionButton
            ariaLabel={`查看发票 ${invoiceNo} 详情`}
            iconOnly
            onClick={() => onOpenDetail({ kind: "invoice", id: row.invoice.id, rowId: row.id })}
            tone="plain"
          >
            <Info aria-hidden="true" size={14} strokeWidth={2.3} />
          </ActionButton>
        </span>
        <span className="output-invoice-collections-tag-row">
          <FinanceTag>{dateOnly(row.invoice.issueDate)}</FinanceTag>
        </span>
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--small-border" data-column-role="identity">
        <TextLine strong value={row.invoice.buyerName} />
        <TextLine muted value={row.invoice.buyerTaxNo} />
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--amount output-invoice-collections-table-cell--small-border" data-column-role="amount">
        <TextLine numeric strong value={formatMoney(row.invoice.totalWithTax)} />
        <TextLine muted numeric value={taxSummary(row.invoice.taxAmount, row.invoice.taxRate)} />
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--small-border" data-column-role="description">
        <TextLine strong value={row.invoice.specificBusinessType} />
        <ExpandableCellText
          expanded={invoiceCellExpanded}
          onToggle={() => onToggleCellExpand(row.id, "invoice-business")}
          text={row.invoice.taxableItemName}
          threshold={18}
        />
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--left-border output-invoice-collections-table-cell--status output-invoice-collection-status-cell" data-column-role="status">
        <FinanceTag tone="info">{row.collectionStatus.label || "待处理"}</FinanceTag>
        <span className="output-invoice-collections-cell-stack">
          <span className="output-invoice-collections-table-text output-invoice-collections-table-text--muted output-invoice-collections-table-text--numeric">
            已收 {formatMoney(row.collectionStatus.collectedAmount)} / 待收 {formatMoney(row.collectionStatus.pendingAmount)}
          </span>
          <span className="output-invoice-collections-action-row">
            {canMutateData ? (
              <>
                <ActionButton onClick={() => onOpenWorkflow({ kind: "collectionStatus", rowId: row.id })} tone="outline">
                  状态/提醒
                </ActionButton>
                <ActionButton onClick={() => onOpenWorkflow({ kind: "redRelation", rowId: row.id })} tone="plain">
                  红蓝票
                </ActionButton>
              </>
            ) : null}
          </span>
        </span>
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--left-border" data-column-role="identity">
        {bank ? (
          <>
            <ExpandableCellText
              expanded={expandedCells.has(`${row.id}:bank-name`)}
              onToggle={() => onToggleCellExpand(row.id, "bank-name")}
              text={bank.counterpartyName}
            />
            <span className="output-invoice-collections-tag-row">
              <FinanceTag>{bank.tradeTime || "收款日期为空"}</FinanceTag>
              {bank.relationStatus === "candidate" ? <FinanceTag tone="warning">候选</FinanceTag> : null}
              {bank.detailAvailable ? (
                <ActionButton
                  ariaLabel={`查看流水 ${bank.counterpartyName || bank.id} 详情`}
                  iconOnly
                  onClick={() => onOpenDetail({ kind: "bank", id: bank.id, rowId: row.id })}
                  tone="plain"
                >
                  <Info aria-hidden="true" size={14} strokeWidth={2.3} />
                </ActionButton>
              ) : null}
            </span>
          </>
        ) : <EmptyValue />}
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--amount output-invoice-collections-table-cell--small-border" data-column-role="amount">
        {bank ? (
          <>
            <TextLine numeric strong value={formatMoney(row.bank.hasMultiple && row.bank.receivedTotal ? row.bank.receivedTotal : bank.amount)} />
            <span className="output-invoice-collections-tag-row output-invoice-collections-tag-row--right">
              {row.bank.hasMultiple ? <FinanceTag tone="info">多笔</FinanceTag> : null}
              <FinanceTag tone={bank.directionLabel === "收入" ? "success" : "neutral"}>{bank.directionLabel || "收入"}</FinanceTag>
              {bankAccountLabel ? <FinanceTag>{bankAccountLabel}</FinanceTag> : null}
            </span>
          </>
        ) : <EmptyValue />}
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--small-border" data-column-role="description">
        {bank ? (
          <>
            <ExpandableCellText
              expanded={bankSummaryCellExpanded}
              onToggle={() => onToggleCellExpand(row.id, "bank-summary")}
              text={bank.summary || bank.remark}
            />
          </>
        ) : <EmptyValue />}
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--left-border" data-column-role="action">
        <TextLine strong value={row.receipt.label} />
        <span className="output-invoice-collections-cell-stack">
          <ActionButton
            onClick={() => onOpenWorkflow({ kind: "receiptHistory", invoiceId: row.invoice.id, rowId: row.id })}
            tone="outline"
          >
            已出收据
          </ActionButton>
          {canMutateData ? (
            <ActionButton
              disabled={!row.receipt.previewAvailable}
              onClick={() => onOpenWorkflow({ kind: "receiptPreview", rowId: row.id })}
              tone="primary"
            >
              待出收据
            </ActionButton>
          ) : null}
        </span>
      </td>
    </tr>
  );
}

function GroupHeader({ label, span, group }: { label: string; span: number; group: "invoice" | "status" | "bank" | "receipt" }) {
  return (
    <th
      className={cx(
        "output-invoice-collections-table-group-header",
        `output-invoice-collections-table-group-header--${group}`,
        group !== "invoice" && "output-invoice-collections-table-cell--left-border",
      )}
      colSpan={span}
      scope="colgroup"
    >
      {label}
    </th>
  );
}

function SortButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      aria-label={`${label} 排序`}
      className="output-invoice-collections-sort-button"
      onClick={onClick}
      title={`${label} 排序`}
      type="button"
    >
      <ArrowUpDown aria-hidden="true" size={14} strokeWidth={2.3} />
    </button>
  );
}

function TextLine({
  value,
  strong = false,
  muted = false,
  numeric = false,
}: {
  value: string | number | null | undefined;
  strong?: boolean;
  muted?: boolean;
  numeric?: boolean;
}) {
  const text = value == null || value === "" ? "—" : String(value);
  if (text === "—") {
    return <EmptyValue />;
  }
  return (
    <span
      className={cx(
        "output-invoice-collections-table-text",
        strong && "output-invoice-collections-table-text--strong",
        muted && "output-invoice-collections-table-text--muted",
        numeric && "output-invoice-collections-table-text--numeric",
      )}
      title={text}
    >
      {text}
    </span>
  );
}

function EmptyValue() {
  return <span className="output-invoice-collections-empty-value">—</span>;
}

function FinanceTag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "info" | "success" | "warning" }) {
  return <span className={`output-invoice-collections-table-tag output-invoice-collections-table-tag--${tone}`}>{children}</span>;
}

function ActionButton({
  children,
  onClick,
  ariaLabel,
  tone,
  iconOnly = false,
  disabled = false,
}: {
  children: ReactNode;
  onClick: () => void;
  ariaLabel?: string;
  tone: "plain" | "outline" | "primary";
  iconOnly?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      aria-label={ariaLabel}
      className={cx(
        "output-invoice-collections-table-action",
        `output-invoice-collections-table-action--${tone}`,
        iconOnly && "output-invoice-collections-table-action--icon",
      )}
      disabled={disabled}
      onClick={onClick}
      title={ariaLabel}
      type="button"
    >
      {children}
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
    <div className="output-invoice-collections-pagination">
      <label className="output-invoice-collections-pagination-size">
        <span>每页行数</span>
        <select
          aria-label="每页行数"
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
          value={pageSize}
        >
          {[20, 50, 100].map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </label>
      <span className="output-invoice-collections-pagination-range">{displayedRange(currentPage, pageSize, total)}</span>
      <span className="output-invoice-collections-pagination-actions">
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
  return columnId === "collectionStatus" || columnId === "bankCounterparty" || columnId === "receiptStatus";
}

function accountLabel(bankName: string, accountLast4: string) {
  return [bankName, accountLast4].filter(Boolean).join(" ").trim();
}

function taxSummary(taxAmount: string, taxRate: string) {
  const amount = formatMoney(taxAmount);
  if (amount === "—" && !taxRate) {
    return "";
  }
  return [amount, taxRate].filter((value) => value && value !== "—").join(" / ");
}

function displayInvoiceNo(row: OutputInvoiceCollectionRow) {
  const invoice = row.invoice;
  if (invoice.displayNo) {
    return invoice.displayNo;
  }
  if (invoice.digitalInvoiceNo) {
    return invoice.digitalInvoiceNo;
  }
  return [invoice.invoiceCode, invoice.invoiceNo].filter(Boolean).join(" ") || "—";
}

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value || "—";
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

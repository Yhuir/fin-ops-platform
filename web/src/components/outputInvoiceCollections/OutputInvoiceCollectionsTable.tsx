import { ArrowUpDown, Info } from "lucide-react";
import type { MutableRefObject, ReactNode } from "react";

import type {
  OutputInvoiceCollectionDetailTarget,
  OutputInvoiceCollectionFilter,
  OutputInvoiceCollectionFilterFieldConfig,
  OutputInvoiceCollectionFilterOption,
  OutputInvoiceCollectionRow,
  OutputInvoiceCollectionSortDirection,
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
  expandedCells: Set<string>;
  onToggleCellExpand: (rowId: string, cellId: string) => void;
  onOpenDetail: (target: OutputInvoiceCollectionDetailTarget) => void;
  onFilterApply: (filter: OutputInvoiceCollectionFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OutputInvoiceCollectionSortDirection) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  emptyStateMessage?: string;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
};

type Column = {
  id: string;
  label: string;
  subLabel?: string;
  align?: "left" | "right";
  field?: string;
  extraFilters?: Array<{ field: string; label: string }>;
  group: "invoice" | "status" | "bank";
};

const columns: Column[] = [
  { id: "invoiceNo", label: "发票号码", field: "invoice_no", extraFilters: [{ field: "invoice_date", label: "开票日期" }], group: "invoice" },
  { id: "buyer", label: "购方", field: "buyer_name", group: "invoice" },
  { id: "totalWithTax", label: "价税合计", subLabel: "税额/税率", field: "total_with_tax", align: "right", group: "invoice" },
  { id: "business", label: "业务/货物劳务", field: "taxable_item_name", group: "invoice" },
  { id: "collectionStatus", label: "收款状态", field: "collection_status", group: "status" },
  { id: "bankCounterparty", label: "付款方/日期", field: "bank_counterparty_name", group: "bank" },
  { id: "bankAmount", label: "收款金额", field: "bank_amount", align: "right", group: "bank" },
  { id: "bankSummary", label: "摘要", field: "bank_summary", group: "bank" },
];

const defaultFilterConfigs: Record<string, OutputInvoiceCollectionFilterFieldConfig> = {
  invoice_no: { field: "invoice_no", label: "发票号码", mode: "text", sortable: true, operators: ["contains", "equals"] },
  invoice_date: { field: "invoice_date", label: "开票日期", mode: "date", sortable: true, operators: ["between", "equals"] },
  buyer_name: { field: "buyer_name", label: "购方", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  total_with_tax: { field: "total_with_tax", label: "价税合计", mode: "money", sortable: true, operators: ["between", "equals"] },
  taxable_item_name: { field: "taxable_item_name", label: "业务/货物劳务", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  collection_status: { field: "collection_status", label: "收款状态", mode: "enum_multi", sortable: true, operators: ["in"] },
  bank_counterparty_name: { field: "bank_counterparty_name", label: "付款方/日期", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  bank_amount: { field: "bank_amount", label: "收款金额", mode: "money", sortable: true, operators: ["between", "equals"] },
  bank_summary: { field: "bank_summary", label: "摘要", mode: "text", sortable: true, operators: ["contains"] },
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
  expandedCells,
  onToggleCellExpand,
  onOpenDetail,
  onFilterApply,
  onFilterClear,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  emptyStateMessage = "当前条件下没有销项发票收款记录。",
  tableWrapRef,
}: OutputInvoiceCollectionsTableProps) {
  const configsByField = new Map(filterConfigs.map((config) => [config.field, config]));
  const fieldConfig = (field: string) => configsByField.get(field) ?? defaultFilterConfigs[field];
  const currentFilter = (field: string) => filters.find((filter) => filter.field === field);

  return (
    <div className="output-invoice-collections-table-frame">
      <div ref={tableWrapRef} className="output-invoice-collections-table-shell" data-testid="output-invoice-collections-table-shell">
        <table aria-label="销项发票收款情况表" className="output-invoice-collections-table">
          <colgroup>
            {columns.map((column) => <col className={`output-invoice-collections-col-${column.id}`} key={column.id} />)}
          </colgroup>
          <thead>
            <tr>
              <GroupHeader group="invoice" label="销项发票" span={4} />
              <GroupHeader group="status" label="收款状态" span={1} />
              <GroupHeader group="bank" label="收入流水" span={3} />
            </tr>
            <tr aria-label={sortField && sortDirection ? `${sortField} ${sortDirection}` : undefined}>
              {columns.map((column) => {
                const config = column.field ? fieldConfig(column.field) : undefined;
                return (
                  <th
                    className={cx(
                      "output-invoice-collections-table-sub-header",
                      `output-invoice-collections-table-sub-header--${column.group}`,
                      column.align === "right" && "output-invoice-collections-table-cell--amount",
                      firstColumnInGroup(column.id) && "output-invoice-collections-table-cell--left-border",
                    )}
                    key={column.id}
                    scope="col"
                  >
                    <span className={cx("output-invoice-collections-table-header-stack", column.align === "right" && "output-invoice-collections-table-header-stack--right")}>
                      {column.field && config ? (
                        <OutputInvoiceCollectionFilterMenu
                          currentFilter={currentFilter(column.field) as OutputInvoiceCollectionFilterValue | null}
                          fieldConfig={{ ...config, label: column.label }}
                          onApply={onFilterApply}
                          onClear={onFilterClear}
                          onSort={(direction) => onSortChange(column.field!, direction)}
                          options={filterOptions[column.field] ?? []}
                        />
                      ) : <span>{column.label}</span>}
                      {column.field && config?.sortable !== false ? (
                        <SortButton label={column.label} onClick={() => onSortChange(column.field!)} />
                      ) : null}
                      {column.extraFilters?.map((extra) => {
                        const extraConfig = fieldConfig(extra.field);
                        return extraConfig ? (
                          <OutputInvoiceCollectionFilterMenu
                            key={extra.field}
                            currentFilter={currentFilter(extra.field) as OutputInvoiceCollectionFilterValue | null}
                            fieldConfig={{ ...extraConfig, label: extra.label }}
                            onApply={onFilterApply}
                            onClear={onFilterClear}
                            onSort={(direction) => onSortChange(extra.field, direction)}
                            options={filterOptions[extra.field] ?? []}
                          />
                        ) : null;
                      })}
                      {column.subLabel ? <span className="output-invoice-collections-table-header-sub-label">{column.subLabel}</span> : null}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td className="output-invoice-collections-table-state-cell" colSpan={columns.length}>{emptyStateMessage}</td></tr>
            ) : rows.map((row) => (
              <DataRow
                expandedCells={expandedCells}
                key={row.id}
                onOpenDetail={onOpenDetail}
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

function DataRow({
  row,
  expandedCells,
  onToggleCellExpand,
  onOpenDetail,
}: {
  row: OutputInvoiceCollectionRow;
  expandedCells: Set<string>;
  onToggleCellExpand: (rowId: string, cellId: string) => void;
  onOpenDetail: (target: OutputInvoiceCollectionDetailTarget) => void;
}) {
  const bank = row.bank.primary;
  const invoiceRelationTarget = relationListTarget(row, "invoice");
  const bankRelationTarget = relationListTarget(row, "bank");
  const statusCode = row.collectionStatus.code || "pending_collection";
  const showCollectionAmounts = ["pending_collection", "partial_collected", "collected"].includes(statusCode);

  return (
    <tr className="output-invoice-collections-table-row">
      <td className="output-invoice-collections-table-cell" data-column-role="identity">
        <span className="output-invoice-collections-inline-row">
          <TextLine strong value={displayInvoiceNo(row)} />
          <IconDetailButton
            label={`查看发票 ${displayInvoiceNo(row)} 详情`}
            onClick={() => onOpenDetail({ kind: "invoice", id: row.invoice.id, rowId: row.id })}
          />
        </span>
        <span className="output-invoice-collections-tag-row">
          <FinanceTag>{dateOnly(row.invoice.issueDate)}</FinanceTag>
          {invoiceRelationTarget ? (
            <RelationButton
              label={`红蓝票 · ${row.invoiceRelations.relationCount}`}
              onClick={() => onOpenDetail(invoiceRelationTarget)}
            />
          ) : null}
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
          expanded={expandedCells.has(`${row.id}:invoice-business`)}
          onToggle={() => onToggleCellExpand(row.id, "invoice-business")}
          text={row.invoice.taxableItemName}
          threshold={18}
        />
      </td>
      <td className={cx(
        "output-invoice-collections-table-cell",
        "output-invoice-collections-table-cell--left-border",
        "output-invoice-collections-table-cell--status",
        "output-invoice-collection-status-cell",
      )} data-column-role="status">
        <span className={`output-invoice-collection-status output-invoice-collection-status--${statusCode}`}>
          {row.collectionStatus.label || "待收款"}
        </span>
        {row.collectionStatus.reason ? <TextLine muted value={row.collectionStatus.reason} /> : null}
        {showCollectionAmounts ? (
          <TextLine
            muted
            numeric
            value={`已收 ${formatMoney(row.collectionStatus.collectedAmount)} / 待收 ${formatMoney(row.collectionStatus.pendingAmount)}`}
          />
        ) : null}
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--left-border" data-column-role="identity">
        {bank ? (
          <>
            <span className="output-invoice-collections-inline-row">
              <ExpandableCellText
                expanded={expandedCells.has(`${row.id}:bank-name`)}
                onToggle={() => onToggleCellExpand(row.id, "bank-name")}
                text={bank.counterpartyName}
              />
              {bank.detailAvailable ? (
                <IconDetailButton
                  label={`查看流水 ${bank.counterpartyName || bank.id} 详情`}
                  onClick={() => onOpenDetail({ kind: "bank", id: bank.id, rowId: row.id })}
                />
              ) : null}
            </span>
            <span className="output-invoice-collections-tag-row">
              <FinanceTag>{dateOnly(bank.tradeTime)}</FinanceTag>
              {bankRelationTarget ? (
                <RelationButton
                  label={`收入流水 · ${row.bank.relationCount}`}
                  onClick={() => onOpenDetail(bankRelationTarget)}
                />
              ) : null}
            </span>
          </>
        ) : <EmptyValue />}
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--amount output-invoice-collections-table-cell--small-border" data-column-role="amount">
        {bank ? (
          <>
            <TextLine numeric strong value={formatMoney(row.bank.receivedTotal || bank.amount)} />
            <span className="output-invoice-collections-tag-row output-invoice-collections-tag-row--right">
              <FinanceTag tone={bank.directionLabel === "收入" ? "success" : "neutral"}>{bank.directionLabel || "收入"}</FinanceTag>
              {accountLabel(bank.bankName, bank.accountLast4) ? <FinanceTag>{accountLabel(bank.bankName, bank.accountLast4)}</FinanceTag> : null}
            </span>
          </>
        ) : <EmptyValue />}
      </td>
      <td className="output-invoice-collections-table-cell output-invoice-collections-table-cell--small-border" data-column-role="description">
        {bank ? (
          <ExpandableCellText
            expanded={expandedCells.has(`${row.id}:bank-summary`)}
            onToggle={() => onToggleCellExpand(row.id, "bank-summary")}
            text={bank.summary || bank.remark}
          />
        ) : <EmptyValue />}
      </td>
    </tr>
  );
}

function GroupHeader({ label, span, group }: { label: string; span: number; group: "invoice" | "status" | "bank" }) {
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
    <button aria-label={`${label} 排序`} className="output-invoice-collections-sort-button" onClick={onClick} title={`${label} 排序`} type="button">
      <ArrowUpDown aria-hidden="true" size={14} strokeWidth={2.3} />
    </button>
  );
}

function IconDetailButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button aria-label={label} className="output-invoice-collections-table-action output-invoice-collections-table-action--plain output-invoice-collections-table-action--icon" onClick={onClick} title={label} type="button">
      <Info aria-hidden="true" size={14} strokeWidth={2.3} />
    </button>
  );
}

function RelationButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button className="output-invoice-collections-table-action output-invoice-collections-relation-count-button" onClick={onClick} type="button">
      {label}
    </button>
  );
}

function TextLine({ value, strong = false, muted = false, numeric = false }: {
  value: string | number | null | undefined;
  strong?: boolean;
  muted?: boolean;
  numeric?: boolean;
}) {
  const text = value == null || value === "" ? "—" : String(value);
  if (text === "—") return <EmptyValue />;
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

function FinanceTag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "success" }) {
  return <span className={`output-invoice-collections-table-tag output-invoice-collections-table-tag--${tone}`}>{children}</span>;
}

function PaginationControls({ page, pageSize, total, onPageChange, onPageSizeChange }: {
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
        <select aria-label="每页行数" onChange={(event) => onPageSizeChange(Number(event.target.value))} value={pageSize}>
          {[20, 50, 100].map((option) => <option key={option} value={option}>{option}</option>)}
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

function relationListTarget(
  row: OutputInvoiceCollectionRow,
  relationKind: NonNullable<OutputInvoiceCollectionDetailTarget["relationKind"]>,
): OutputInvoiceCollectionDetailTarget | null {
  const relation = relationKind === "bank" ? row.bank : row.invoiceRelations;
  if (relation.detailMode !== "list" || Number(relation.relationCount ?? 0) <= 1) return null;
  const scopeKey = row.invoice.issueDate.slice(0, 7);
  return {
    kind: "relationList",
    id: row.id,
    rowId: row.id,
    relationKind,
    scopeKey: /^\d{4}-\d{2}$/.test(scopeKey) ? scopeKey : undefined,
  };
}

function displayedRange(page: number, pageSize: number, total: number) {
  if (total <= 0) return "0-0 / 0";
  const from = (page - 1) * pageSize + 1;
  return `${from}-${Math.min(page * pageSize, total)} / ${total}`;
}

function firstColumnInGroup(columnId: string) {
  return columnId === "collectionStatus" || columnId === "bankCounterparty";
}

function accountLabel(bankName: string, accountLast4: string) {
  return [bankName, accountLast4].filter(Boolean).join(" ").trim();
}

function taxSummary(taxAmount: string, taxRate: string) {
  return [formatMoney(taxAmount), taxRate].filter((value) => value && value !== "—").join(" / ");
}

function displayInvoiceNo(row: OutputInvoiceCollectionRow) {
  const invoice = row.invoice;
  return invoice.displayNo || invoice.digitalInvoiceNo || [invoice.invoiceCode, invoice.invoiceNo].filter(Boolean).join(" ") || "—";
}

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  if (!Number.isFinite(parsed)) return value || "—";
  return parsed.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function dateOnly(value: string) {
  if (!value) return "日期为空";
  return value.includes("T") ? value.split("T")[0] : value;
}

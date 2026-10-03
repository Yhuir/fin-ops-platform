import BankSplitChips from "../../features/bankSplits/BankSplitChips";
import { ListBox, Select } from "@heroui/react";
import { ArrowUpDown, Info } from "lucide-react";
import type { ReactNode } from "react";

import type {
  OutputInvoiceCollectionDetailTarget,
  OutputInvoiceCollectionFilter,
  OutputInvoiceCollectionFilterFieldConfig,
  OutputInvoiceCollectionFilterOption,
  OutputInvoiceCollectionRow,
  OutputInvoiceCollectionRowsResponse,
  OutputInvoiceCollectionSortDirection,
} from "../../features/outputInvoiceCollections/types";
import { formatMoney } from "../../features/money";
import {
  EmptyValue as FinanceEmptyValue,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTablePagination,
  FinanceTableRow,
  type FinanceTableColumnRole,
} from "../common/FinanceTable";
import ExpandableCellText from "./ExpandableCellText";
import OutputInvoiceCollectionFilterMenu, { type OutputInvoiceCollectionFilterValue } from "./OutputInvoiceCollectionFilterMenu";

type OutputInvoiceCollectionsTableProps = {
  rows: OutputInvoiceCollectionRow[];
  page: number;
  pageSize: number;
  total: number;
  summary?: OutputInvoiceCollectionRowsResponse["summary"];
  refreshing?: boolean;
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
};

type Column = {
  id: string;
  label: string;
  align?: "left" | "right";
  field?: string;
  extraFilters?: Array<{ field: string; label: string }>;
  group: "invoice" | "status" | "bank";
};

const columns: Column[] = [
  { id: "invoiceNo", label: "发票号码", field: "invoice_no", extraFilters: [{ field: "invoice_date", label: "开票日期" }], group: "invoice" },
  { id: "buyer", label: "购方", field: "buyer_name", group: "invoice" },
  { id: "totalWithTax", label: "价税合计", extraFilters: [{ field: "tax_rate", label: "税率" }], field: "total_with_tax", align: "right", group: "invoice" },
  { id: "business", label: "业务/货物劳务", field: "taxable_item_name", group: "invoice" },
  { id: "collectionStatus", label: "状态", field: "collection_status", group: "status" },
  { id: "bankCounterparty", label: "付款方/日期", field: "bank_counterparty_name", group: "bank" },
  { id: "bankAmount", label: "收款金额", field: "bank_amount", align: "right", group: "bank" },
  { id: "bankSummary", label: "摘要", field: "bank_summary", group: "bank" },
];

const defaultFilterConfigs: Record<string, OutputInvoiceCollectionFilterFieldConfig> = {
  invoice_no: { field: "invoice_no", label: "发票号码", mode: "text", sortable: true, operators: ["contains", "equals"] },
  invoice_date: { field: "invoice_date", label: "开票日期", mode: "date", sortable: true, operators: ["between", "equals"] },
  buyer_name: { field: "buyer_name", label: "购方", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  total_with_tax: { field: "total_with_tax", label: "价税合计", mode: "money", sortable: true, operators: ["between", "equals"] },
  tax_rate: { field: "tax_rate", label: "税率", mode: "enum_multi", sortable: true, operators: ["in"] },
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
  summary,
  refreshing = false,
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
}: OutputInvoiceCollectionsTableProps) {
  const configsByField = new Map(filterConfigs.map((config) => [config.field, config]));
  const fieldConfig = (field: string) => configsByField.get(field) ?? defaultFilterConfigs[field];
  const currentFilter = (field: string) => filters.find((filter) => filter.field === field);

  return (
    <div
      aria-busy={refreshing}
      className="finance-page-table-frame output-invoice-collections-table-frame"
    >
      {refreshing ? <span className="output-invoice-collections-busy" role="progressbar" aria-label="正在加载收款情况" /> : null}
      <FinanceTable
        ariaLabel="销项发票收款情况表"
        className="output-invoice-collections-table"
        footer={(
          <PaginationControls
            onPageChange={onPageChange}
            onPageSizeChange={onPageSizeChange}
            page={page}
            pageSize={pageSize}
            total={total}
          />
        )}
        header={<div className="output-invoice-collections-group-headings" aria-label="当前筛选合计">
          {(["invoice", "status", "bank"] as const).map(group => (
            <div key={group} className={`output-invoice-collections-group-header output-invoice-collections-table-sub-header--${group}`}>
              <span className="output-invoice-collections-group-summary">
                <strong>{group === "invoice" ? "销项发票" : group === "bank" ? "收入流水" : "收款状态"}</strong>
                {group === "invoice" ? <>
                  <span title="当前筛选全部发票的含税金额，红票按负数计入">含税金额合计 <b>{summary ? formatMoney(summary.totalWithTax) : "—"}</b></span>
                  <span title="当前筛选全部发票的不含税金额，红票按负数计入">不含税金额合计 <b>{summary ? formatMoney(summary.amountWithoutTax) : "—"}</b></span>
                </> : group === "bank" ? <span title="当前筛选发票可唯一归属的收入用途金额，已去重；不等于父流水原始金额合计">收入合计 <b>{summary ? formatMoney(summary.collectedAmount) : "—"}</b></span> : null}
              </span>
            </div>
          ))}
        </div>}
        minWidth={1246}
        selectableText
        scrollMode="contained"
      >
        <FinanceTableHeader>
          {columns.map((column) => {
            const config = column.field ? fieldConfig(column.field) : undefined;
            return (
              <FinanceTableColumn
                className={cx(
                  "output-invoice-collections-table-sub-header",
                  `output-invoice-collections-table-sub-header--${column.group}`,
                  `output-invoice-collections-col-${column.id}`,
                  firstColumnInGroup(column.id) && "output-invoice-collections-table-cell--left-border",
                )}
                columnRole={columnRole(column)}
                id={column.id}
                isRowHeader={column.id === "invoiceNo"}
                key={column.id}
              >
                <span className="output-invoice-collections-table-column-heading">
                  <span className="output-invoice-collections-table-header-stack">
                    {column.field && column.field !== "collection_status" && config ? (
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
                        <span key={extra.field} className="output-invoice-collections-table-header-sub-label"><OutputInvoiceCollectionFilterMenu
                          currentFilter={currentFilter(extra.field) as OutputInvoiceCollectionFilterValue | null}
                          fieldConfig={{ ...extraConfig, label: extra.label }}
                          onApply={onFilterApply}
                          onClear={onFilterClear}
                          onSort={(direction) => onSortChange(extra.field, direction)}
                          options={filterOptions[extra.field] ?? []}
                        /></span>
                      ) : null;
                    })}
                  </span>
                </span>
              </FinanceTableColumn>
            );
          })}
        </FinanceTableHeader>
        <FinanceTableBody>
          {rows.length === 0 ? (
            <FinanceTableRow id="empty" textValue={emptyStateMessage}>
              {columns.map((column, index) => (
                <FinanceTableCell columnRole={columnRole(column)} key={column.id} textValue={index === 0 ? emptyStateMessage : "—"}>
                  {index === 0 ? emptyStateMessage : <FinanceEmptyValue />}
                </FinanceTableCell>
              ))}
            </FinanceTableRow>
          ) : rows.map((row) => (
            <DataRow
              expandedCells={expandedCells}
              key={row.id}
              onOpenDetail={onOpenDetail}
              onToggleCellExpand={onToggleCellExpand}
              row={row}
            />
          ))}
        </FinanceTableBody>
      </FinanceTable>
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
  const polarity = invoicePolarityPresentation(row.invoice.polarity);
  const reversalTargetInvoiceNos = row.invoice.reversalTargetInvoiceNos;
  const businessTextValue = [
    row.invoice.specificBusinessType,
    row.invoice.taxableItemName,
    ...reversalTargetInvoiceNos,
  ].filter(Boolean).join(" ");

  return (
    <FinanceTableRow className="output-invoice-collections-table-row" id={row.id} textValue={displayInvoiceNo(row)}>
      <FinanceTableCell className="output-invoice-collections-table-cell" columnRole="identity" textValue={displayInvoiceNo(row)}>
        <span className="output-invoice-collections-inline-row">
          <TextLine strong value={displayInvoiceNo(row)} />
          <IconDetailButton
            label={`查看发票 ${displayInvoiceNo(row)} 详情`}
            onClick={() => onOpenDetail({ kind: "invoice", id: row.invoice.id, rowId: row.id })}
          />
        </span>
        <span className="output-invoice-collections-tag-row">
          <FinanceTag>{dateOnly(row.invoice.issueDate)}</FinanceTag>
          <FinanceTag tone={polarity.tone}>{polarity.label}</FinanceTag>
          {invoiceRelationTarget ? (
            <RelationButton
              label={`红蓝票 · ${row.invoiceRelations.relationCount}`}
              onClick={() => onOpenDetail(invoiceRelationTarget)}
            />
          ) : null}
        </span>
      </FinanceTableCell>
      <FinanceTableCell className="output-invoice-collections-table-cell output-invoice-collections-table-cell--small-border" columnRole="identity" textValue={row.invoice.buyerName}>
        <TextLine strong value={row.invoice.buyerName} />
        <TextLine muted value={row.invoice.buyerTaxNo} />
      </FinanceTableCell>
      <FinanceTableCell className="output-invoice-collections-table-cell output-invoice-collections-table-cell--amount output-invoice-collections-table-cell--small-border" columnRole="amount" textValue={row.invoice.totalWithTax}>
        <span className="inline-flex items-baseline justify-end"><TextLine numeric strong value={formatMoney(row.invoice.totalWithTax, "—")} />{row.invoice.inferredFields?.includes("totalWithTax") && <small className="text-default-500">（推算）</small>}</span>
        <span className="output-invoice-collections-tax-rate" title={row.invoice.inferredFields?.includes("taxRate") ? "按税额与不含税金额计算的比例，不代表已核实的票面税率" : undefined}>{row.invoice.taxRate}</span>
      </FinanceTableCell>
      <FinanceTableCell className="output-invoice-collections-table-cell output-invoice-collections-table-cell--small-border" columnRole="description" textValue={businessTextValue}>
        <TextLine strong value={row.invoice.specificBusinessType} />
        <ExpandableCellText
          expanded={expandedCells.has(`${row.id}:invoice-business`)}
          onToggle={() => onToggleCellExpand(row.id, "invoice-business")}
          text={row.invoice.taxableItemName}
          threshold={18}
        />
        {reversalTargetInvoiceNos.length > 0 ? (
          <TextLine muted value={`冲红蓝票：${reversalTargetInvoiceNos.join("；")}`} />
        ) : null}
      </FinanceTableCell>
      <FinanceTableCell className={cx(
        "output-invoice-collections-table-cell",
        "output-invoice-collections-table-cell--left-border",
        "output-invoice-collections-table-cell--status",
      )} columnRole="status" textValue={row.collectionStatus.label}>
        <div className="output-invoice-collection-status-content">
          <span className={`output-invoice-collection-status output-invoice-collection-status--${statusCode}`}>
            {row.collectionStatus.label}
          </span>
          {showCollectionAmounts ? (
            <span className="output-invoice-collection-amounts">
              <span className="output-invoice-collection-amount output-invoice-collection-amount--collected">
                已收 {formatMoney(row.collectionStatus.collectedAmount)}
              </span>
              <span className="output-invoice-collection-amount output-invoice-collection-amount--pending">
                待收 {formatMoney(row.collectionStatus.pendingAmount)}
              </span>
            </span>
          ) : null}
        </div>
      </FinanceTableCell>
      <FinanceTableCell className="output-invoice-collections-table-cell output-invoice-collections-table-cell--left-border" columnRole="identity" textValue={bank?.counterpartyName ?? "—"}>
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
                  label={`收入流水 · ${row.bank.originalTransactionCount}`}
                  onClick={() => onOpenDetail(bankRelationTarget)}
                />
              ) : null}
            </span>
          </>
        ) : <EmptyValue />}
      </FinanceTableCell>
      <FinanceTableCell className="output-invoice-collections-table-cell output-invoice-collections-table-cell--amount output-invoice-collections-table-cell--small-border" columnRole="amount" textValue={row.bank.originalAmount || "—"}>
        {bank ? (
          <>
            <TextLine numeric strong value={formatMoney(row.bank.originalAmount, "—")} />
            <span className="output-invoice-collections-tag-row output-invoice-collections-tag-row--right">
              <FinanceTag tone={bank.directionLabel === "收入" ? "success" : "neutral"}>{bank.directionLabel || "收入"}</FinanceTag>
              {accountLabel(bank.bankName, bank.accountLast4) ? <FinanceTag>{accountLabel(bank.bankName, bank.accountLast4)}</FinanceTag> : null}
            </span>
            {row.bank.bankSplitParts?.length ? <BankSplitChips parts={row.bank.bankSplitParts} /> : null}
          </>
        ) : <EmptyValue />}
      </FinanceTableCell>
      <FinanceTableCell className="output-invoice-collections-table-cell output-invoice-collections-table-cell--small-border" columnRole="description" textValue={bank?.summary || bank?.remark || "—"}>
        {bank ? (
          <ExpandableCellText
            expanded={expandedCells.has(`${row.id}:bank-summary`)}
            onToggle={() => onToggleCellExpand(row.id, "bank-summary")}
            text={bank.summary || bank.remark}
          />
        ) : <EmptyValue />}
      </FinanceTableCell>
    </FinanceTableRow>
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

function FinanceTag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "info" | "success" | "danger" }) {
  return <span className={`output-invoice-collections-table-tag output-invoice-collections-table-tag--${tone}`}>{children}</span>;
}

function PaginationControls({ page, pageSize, total, onPageChange, onPageSizeChange }: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  return (
    <div className="output-invoice-collections-pagination">
      <Select aria-label="每页发票张数" onSelectionChange={(key) => onPageSizeChange(Number(key))} selectedKey={String(pageSize)}>
        <Select.Trigger className="output-invoice-collections-pagination-size">
          <Select.Value />
          <Select.Indicator />
        </Select.Trigger>
        <Select.Popover>
          <ListBox>
            {[20, 50, 100].map((option) => (
              <ListBox.Item id={String(option)} key={option} textValue={`${option} 张/页`}>
                {option} 张/页
              </ListBox.Item>
            ))}
          </ListBox>
        </Select.Popover>
      </Select>
      <FinanceTablePagination className="finance-table-pagination--fit" compact onPageChange={onPageChange} page={page} pageSize={pageSize} total={total} />
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

function firstColumnInGroup(columnId: string) {
  return columnId === "collectionStatus" || columnId === "bankCounterparty";
}

function columnRole(column: Column): FinanceTableColumnRole {
  if (column.align === "right") return "amount";
  if (column.group === "status") return "status";
  if (column.id === "invoiceNo" || column.id === "buyer" || column.id === "bankCounterparty") return "identity";
  return "description";
}

function accountLabel(bankName: string, accountLast4: string) {
  return [bankName, accountLast4].filter(Boolean).join(" ").trim();
}


function displayInvoiceNo(row: OutputInvoiceCollectionRow) {
  const invoice = row.invoice;
  return invoice.displayNo || invoice.digitalInvoiceNo || [invoice.invoiceCode, invoice.invoiceNo].filter(Boolean).join(" ") || "—";
}

function dateOnly(value: string) {
  if (!value) return "日期为空";
  return value.includes("T") ? value.split("T")[0] : value;
}

function invoicePolarityPresentation(polarity: OutputInvoiceCollectionRow["invoice"]["polarity"]) {
  if (polarity === "blue") return { label: "蓝字", tone: "info" as const };
  if (polarity === "red") return { label: "红字", tone: "danger" as const };
  return { label: "票面类型未知", tone: "neutral" as const };
}

import { ArrowUpDown, Filter, Info } from "lucide-react";
import { Checkbox, ListBox, PopoverContent, PopoverDialog, PopoverRoot, PopoverTrigger, Select } from "@heroui/react";
import type { MutableRefObject, ReactNode } from "react";
import { useId, useMemo, useState } from "react";

import type {
  InputInvoiceUsageDetailTarget,
  InputInvoiceUsageFilter,
  InputInvoiceUsageFilterFieldConfig,
  InputInvoiceUsageFilterOption,
  InputInvoiceUsageRow,
  InputInvoiceUsageSortDirection,
} from "../../features/inputInvoiceUsage/types";
import { formatMoney } from "../../features/money";
import { formatDateTimeText } from "../../features/dateTime";
import ExpandableCellText from "./ExpandableCellText";
import InputInvoiceUsageFilterMenu from "./InputInvoiceUsageFilterMenu";
import type { InputInvoiceUsageFilterValue } from "./InputInvoiceUsageFilterMenu";
import OaWorkflowStatusChip from "../common/OaWorkflowStatusChip";
import {
  EmptyValue,
  FinanceStatusTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTablePagination,
  FinanceTableRow,
} from "../common/FinanceTable";

type InputInvoiceUsageTableProps = {
  rows: InputInvoiceUsageRow[];
  page: number;
  pageSize: number;
  total: number;
  filterConfigs: InputInvoiceUsageFilterFieldConfig[];
  filterOptions: Record<string, InputInvoiceUsageFilterOption[]>;
  filters: InputInvoiceUsageFilter[];
  sortField: string;
  sortDirection: InputInvoiceUsageSortDirection | "";
  expandedCells: Set<string>;
  onToggleCellExpand: (rowId: string, cellId: string) => void;
  onOpenDetail: (target: InputInvoiceUsageDetailTarget) => void;
  onFilterApply: (filter: { field: string; operator: string; value?: string | null; values?: string[] }) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: InputInvoiceUsageSortDirection) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  emptyStateMessage?: string;
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

function dateOnly(value: string) {
  if (!value) {
    return "日期为空";
  }
  return value.includes("T") ? value.split("T")[0] : value;
}

function classNames(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

function selectedValues(filter?: InputInvoiceUsageFilter | null) {
  if (!filter) {
    return [];
  }
  if (Array.isArray(filter.values)) {
    return filter.values;
  }
  if (typeof filter.value === "string" && filter.value) {
    return [filter.value];
  }
  return [];
}

function directionLabel(value: string) {
  if (value === "outflow" || value === "支" || value === "支出") {
    return "支出";
  }
  if (value === "inflow" || value === "收" || value === "收入") {
    return "收入";
  }
  return value || "收支为空";
}

function bankAccountLabel(bank: InputInvoiceUsageRow["bank"]["primary"]) {
  if (!bank) {
    return "";
  }
  return bank.bankAccount || [bank.bankName, bank.accountLast4].filter(Boolean).join(" ");
}

function HeaderCell({
  label,
  align,
  separated,
  strongSeparated,
  emphasized,
  isRowHeader,
}: {
  label: ReactNode;
  align?: "left" | "right" | "center";
  separated?: boolean;
  strongSeparated?: boolean;
  emphasized?: boolean;
  isRowHeader?: boolean;
}) {
  return (
    <FinanceTableColumn
      className={classNames(
        "input-invoice-usage-table-sub-header",
        align && `input-invoice-usage-table-sub-header--${align}`,
        separated && "input-invoice-usage-table-cell--separator",
        strongSeparated && "input-invoice-usage-table-cell--strong-separator",
        emphasized && "input-invoice-usage-table-cell--payment",
      )}
      columnRole={align === "right" ? "amount" : emphasized ? "status" : "description"}
      isRowHeader={isRowHeader}
    >
      <span className="input-invoice-usage-table-header-stack">{label}</span>
    </FinanceTableColumn>
  );
}

function SortHeaderButton({
  label,
  sortLabel = label,
  active,
  direction,
  onClick,
}: {
  label: string;
  sortLabel?: string;
  active: boolean;
  direction: InputInvoiceUsageSortDirection | "";
  onClick: () => void;
}) {
  const stateLabel = active && direction ? (direction === "asc" ? "升序" : "降序") : "未排序";
  return (
    <button
      aria-label={`按${sortLabel}排序`}
      className={classNames("input-invoice-usage-sort-button", active && "input-invoice-usage-sort-button--active")}
      onClick={onClick}
      title={`${sortLabel}${stateLabel}`}
      type="button"
    >
      <span>{label}</span>
      <ArrowUpDown aria-hidden="true" size={14} />
    </button>
  );
}

function CompositeFilterMenu({
  label,
  columns,
  currentFilters,
  onApply,
  onClear,
}: {
  label: string;
  columns: Array<{ field: string; label: string; options: InputInvoiceUsageFilterOption[] }>;
  currentFilters: InputInvoiceUsageFilter[];
  onApply: (filter: { field: string; operator: string; value?: string | null; values?: string[] }) => void;
  onClear: (field: string) => void;
}) {
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const selectedByField = useMemo(() => {
    const pairs = columns.map((column) => [
      column.field,
      selectedValues(currentFilters.find((filter) => filter.field === column.field)),
    ] as const);
    return new Map(pairs);
  }, [columns, currentFilters]);
  const hasActive = columns.some((column) => (selectedByField.get(column.field) ?? []).length > 0);

  const toggle = (field: string, value: string) => {
    const current = selectedByField.get(field) ?? [];
    const next = current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
    if (next.length === 0) {
      onClear(field);
      return;
    }
    onApply({ field, operator: "in", values: next });
  };

  return (
    <PopoverRoot isOpen={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-controls={open ? menuId : undefined}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`筛选 ${label}`}
        className={classNames(
          "input-invoice-usage-filter-menu__trigger",
          hasActive && "input-invoice-usage-filter-menu__trigger--active",
        )}
      >
        <Filter aria-hidden="true" size={14} />
        <span>{label}</span>
      </PopoverTrigger>
      {open ? (
        <PopoverContent className="input-invoice-usage-filter-menu__popover" containerPadding={12} offset={4} placement="bottom start">
          <PopoverDialog aria-label={`${label}组合筛选`} className="input-invoice-usage-filter-menu__dialog">
            <div
              aria-label={`${label}组合筛选`}
              className="input-invoice-usage-filter-menu__panel input-invoice-usage-filter-menu__panel--composite"
              id={menuId}
              onKeyDown={(event) => {
                if (event.key === "Escape") setOpen(false);
              }}
              role="menu"
            >
              {columns.map((column) => {
                const selected = new Set(selectedByField.get(column.field) ?? []);
                return (
                  <div className="input-invoice-usage-filter-menu__column" key={column.field}>
                    <div className="input-invoice-usage-filter-menu__column-title">{column.label}</div>
                    <button
                      className="input-invoice-usage-filter-menu__item"
                      onClick={() => onClear(column.field)}
                      role="menuitem"
                      type="button"
                    >
                      清空
                    </button>
                    {column.options.length === 0 ? (
                      <div aria-disabled="true" className="input-invoice-usage-filter-menu__item input-invoice-usage-filter-menu__item--disabled" role="menuitem">
                        暂无可选项
                      </div>
                    ) : null}
                    {column.options.map((option) => (
                      <Checkbox
                        aria-label={option.count === undefined ? option.label : `${option.label} ${option.count}`}
                        className="input-invoice-usage-filter-menu__item"
                        isSelected={selected.has(option.value)}
                        key={`${column.field}:${option.value}`}
                        onChange={() => toggle(column.field, option.value)}
                        slot={null}
                      >
                        <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                        <span>{option.count === undefined ? option.label : `${option.label} ${option.count}`}</span>
                      </Checkbox>
                    ))}
                  </div>
                );
              })}
            </div>
          </PopoverDialog>
        </PopoverContent>
      ) : null}
    </PopoverRoot>
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

function RelationCountButton({
  label,
  extraCount,
  onClick,
}: {
  label: string;
  extraCount: number;
  onClick: () => void;
}) {
  if (extraCount <= 0) {
    return null;
  }
  return (
    <button
      aria-label={label}
      className="input-invoice-usage-table-action input-invoice-usage-relation-count-button"
      onClick={onClick}
      title={label}
      type="button"
    >
      {`+${extraCount}`}
    </button>
  );
}

function extraRelationCount(relationCount: number | undefined): number {
  return Math.max(0, Number(relationCount ?? 0) - 1);
}

function relationListTarget(
  row: InputInvoiceUsageRow,
  relationKind: NonNullable<InputInvoiceUsageDetailTarget["relationKind"]>,
): InputInvoiceUsageDetailTarget | null {
  const relation = relationKind === "oa" ? row.oa : relationKind === "bank" ? row.bank : row.invoiceRelations;
  if (relation.detailMode === "list" && Number(relation.relationCount ?? 0) > 1) {
    const scopeKey = row.invoice.issueDate.slice(0, 7);
    return {
      kind: "relationList",
      id: row.id,
      rowId: row.id,
      relationKind,
      scopeKey: /^\d{4}-\d{2}$/.test(scopeKey) ? scopeKey : undefined,
    };
  }
  return null;
}

export default function InputInvoiceUsageTable({
  rows,
  page,
  pageSize,
  total,
  filterConfigs,
  filterOptions,
  filters,
  sortField,
  sortDirection,
  expandedCells,
  onToggleCellExpand,
  onOpenDetail,
  onFilterApply,
  onFilterClear,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  emptyStateMessage = "当前条件下没有进项发票使用记录。",
  tableWrapRef,
}: InputInvoiceUsageTableProps) {
  const configsByField = new Map(filterConfigs.map((config) => [config.field, config]));
  const filterFor = (field: string) => filters.find((filter) => filter.field === field) as InputInvoiceUsageFilterValue | undefined;
  const filterMenu = (field: string, label: string) => {
    const config = configsByField.get(field) ?? {
      field,
      label,
      mode: "enum_multi" as const,
      sortable: true,
      operators: ["in"] as InputInvoiceUsageFilterFieldConfig["operators"],
    };
    return (
      <InputInvoiceUsageFilterMenu
        currentFilter={filterFor(field)}
        fieldConfig={{ ...config, label }}
        onApply={onFilterApply}
        onClear={onFilterClear}
        onSort={(direction) => onSortChange(field, direction)}
        options={filterOptions[field] ?? []}
      />
    );
  };

  return (
    <div className="finance-page-table-frame input-invoice-usage-table-frame">
      <FinanceTable
        ariaLabel="进项发票使用情况表"
        className="input-invoice-usage-table input-invoice-usage-table-shell"
        footer={(
          <div className="input-invoice-usage-pagination">
            <Select aria-label="每页行数" className="input-invoice-usage-pagination-size" onChange={(key) => onPageSizeChange(Number(key))} value={String(pageSize)}>
              <Select.Trigger><Select.Value /></Select.Trigger>
              <Select.Popover><ListBox>{PAGE_SIZE_OPTIONS.map((option) => <ListBox.Item id={String(option)} key={option} textValue={String(option)}>{option}</ListBox.Item>)}</ListBox></Select.Popover>
            </Select>
            <FinanceTablePagination className="finance-table-pagination--fit" compact onPageChange={onPageChange} page={page} pageSize={pageSize} total={total} />
          </div>
        )}
        minWidth={1480}
        scrollMode="contained"
        scrollRef={tableWrapRef}
      >
          <FinanceTableHeader>
              <HeaderCell
                isRowHeader
                label={(
                  <span className="input-invoice-usage-table-column-heading"><span>进项发票</span><SortHeaderButton active={sortField === "invoice_date"} direction={sortField === "invoice_date" ? sortDirection : ""} label="发票号码" sortLabel="开票日期" onClick={() => onSortChange("invoice_date")} /></span>
                )}
              />
              <HeaderCell label={filterMenu("seller_name", "销方名称")} separated />
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
              <HeaderCell label={<span className="input-invoice-usage-table-column-heading"><span>支付状态</span>{filterMenu("payment_status", "支付状态")}</span>} strongSeparated emphasized />
              <HeaderCell
                label={(
                  <CompositeFilterMenu
                    columns={[
                      { field: "oa_applicant", label: "OA申请人", options: filterOptions.oa_applicant ?? [] },
                      { field: "oa_application_type", label: "类型", options: filterOptions.oa_application_type ?? [] },
                    ]}
                    currentFilters={filters}
                    label="OA / OA申请人"
                    onApply={onFilterApply}
                    onClear={onFilterClear}
                  />
                )}
                strongSeparated
              />
              <HeaderCell label={filterMenu("oa_project_name", "项目名称")} separated />
              <HeaderCell label={<span className="input-invoice-usage-table-column-heading"><span>流水</span>{filterMenu("bank_counterparty_name", "对方户名")}</span>} strongSeparated />
              <HeaderCell
                align="right"
                label={(
                  <CompositeFilterMenu
                    columns={[
                      { field: "bank_account", label: "银行账户", options: filterOptions.bank_account ?? [] },
                      { field: "bank_direction", label: "收支", options: filterOptions.bank_direction ?? [] },
                    ]}
                    currentFilters={filters}
                    label="金额"
                    onApply={onFilterApply}
                    onClear={onFilterClear}
                  />
                )}
                separated
              />
              <HeaderCell label="摘要/备注" separated />
          </FinanceTableHeader>
          <FinanceTableBody>
            {rows.length === 0 ? (
              <FinanceTableRow id="input-invoice-usage-empty">
                <FinanceTableCell className="input-invoice-usage-table-state-cell" columnRole="identity">{emptyStateMessage}</FinanceTableCell>
                {Array.from({ length: 9 }, (_, index) => <FinanceTableCell columnRole="description" key={index}><EmptyValue /></FinanceTableCell>)}
              </FinanceTableRow>
            ) : rows.map((row) => {
              const invoiceNo = displayInvoiceNo(row);
              const invoiceCellExpanded = expandedCells.has(`${row.id}:invoice-business`);
              const projectCellExpanded = expandedCells.has(`${row.id}:oa-project`);
              const bankNameCellExpanded = expandedCells.has(`${row.id}:bank-name`);
              const bankRemarkCellExpanded = expandedCells.has(`${row.id}:bank-remark`);
              const oa = row.oa.primary;
              const bank = row.bank.primary;
              const oaRelationTarget = relationListTarget(row, "oa");
              const bankRelationTarget = relationListTarget(row, "bank");
              const invoiceRelationTarget = relationListTarget(row, "invoice");
              const oaExtraCount = extraRelationCount(row.oa.relationCount);
              const bankExtraCount = extraRelationCount(row.bank.relationCount);
              const invoiceExtraCount = extraRelationCount(row.invoiceRelations.relationCount);

              return (
                <FinanceTableRow className="input-invoice-usage-table-row" id={row.id} key={row.id}>
                  <FinanceTableCell className="input-invoice-usage-table-cell" columnRole="identity">
                    <div className="input-invoice-usage-inline-row">
                      <span className="input-invoice-usage-cell-primary" title={invoiceNo}>{invoiceNo}</span>
                      <DetailButton
                        iconOnly
                        label={`查看发票 ${invoiceNo} 详情`}
                        onClick={() => onOpenDetail({ kind: "invoice", id: row.invoice.id, rowId: row.id })}
                      />
                      {invoiceRelationTarget ? (
                        <RelationCountButton
                          extraCount={invoiceExtraCount}
                          label={`查看发票 ${invoiceNo} 关联发票 ${row.invoiceRelations.relationCount} 张`}
                          onClick={() => onOpenDetail(invoiceRelationTarget)}
                        />
                      ) : null}
                    </div>
                    <div className="input-invoice-usage-tag-row">
                      <Tag>{dateOnly(row.invoice.issueDate)}</Tag>
                    </div>
                  </FinanceTableCell>
                  <FinanceTableCell className="input-invoice-usage-table-cell input-invoice-usage-table-cell--separator" columnRole="identity">
                    <div className="input-invoice-usage-cell-primary">{row.invoice.sellerName || "-"}</div>
                    <div className="input-invoice-usage-cell-secondary">{row.invoice.sellerTaxNo || "-"}</div>
                  </FinanceTableCell>
                  <FinanceTableCell className="input-invoice-usage-table-cell input-invoice-usage-table-cell--amount input-invoice-usage-table-cell--separator" columnRole="amount">
                    <div className="input-invoice-usage-money-primary">{formatMoney(row.invoice.totalWithTax)}</div>
                    <div className="input-invoice-usage-cell-secondary">
                      {`${formatMoney(row.invoice.amountWithoutTax)} ${row.invoice.taxRate || "-"} (${formatMoney(row.invoice.taxAmount)})`}
                    </div>
                  </FinanceTableCell>
                  <FinanceTableCell className="input-invoice-usage-table-cell input-invoice-usage-table-cell--separator" columnRole="description">
                    <ExpandableCellText
                      text={row.invoice.taxableItemName}
                      expanded={invoiceCellExpanded}
                      onToggle={() => onToggleCellExpand(row.id, "invoice-business")}
                    />
                  </FinanceTableCell>
                  <FinanceTableCell className="input-invoice-usage-table-cell input-invoice-usage-table-cell--payment input-invoice-usage-table-cell--strong-separator input-invoice-usage-payment-cell" columnRole="status">
                    <Tag tone="warning">{row.paymentStatus.label || "待处理"}</Tag>
                  </FinanceTableCell>
                  <FinanceTableCell className="input-invoice-usage-table-cell input-invoice-usage-table-cell--strong-separator" columnRole="identity">
                    {oa ? (
                      <>
                        <div className="input-invoice-usage-inline-row">
                          <span className="input-invoice-usage-cell-primary">{oa.applicant || "-"}</span>
                          {oa.detailAvailable && !oaRelationTarget ? (
                            <DetailButton
                              iconOnly
                              label={`查看OA ${oa.applicant || oa.id} 详情`}
                              onClick={() => onOpenDetail({ kind: "oa", id: oa.id, rowId: row.id })}
                            />
                          ) : null}
                          {oaRelationTarget ? (
                            <RelationCountButton
                              extraCount={oaExtraCount}
                              label={`查看${oa.applicant || "该发票"}关联OA ${row.oa.relationCount} 条`}
                              onClick={() => onOpenDetail(oaRelationTarget)}
                            />
                          ) : null}
                        </div>
                        <div className="input-invoice-usage-tag-row">
                          <FinanceStatusTag>{oa.applicationType || "类型为空"}</FinanceStatusTag>
                          <OaWorkflowStatusChip status={oa.workflowStatus} />
                          {row.oa.hasMultiple && oa.amount ? (
                            <Tag tone="info">{`合计 ${formatMoney(oa.amount)}`}</Tag>
                          ) : null}
                        </div>
                      </>
                    ) : <EmptyCell />}
                  </FinanceTableCell>
                  <FinanceTableCell className="input-invoice-usage-table-cell input-invoice-usage-table-cell--separator" columnRole="description">
                    {oa ? (
                      <ExpandableCellText
                        text={oa.projectName}
                        expanded={projectCellExpanded}
                        onToggle={() => onToggleCellExpand(row.id, "oa-project")}
                      />
                    ) : <EmptyCell />}
                  </FinanceTableCell>
                  <FinanceTableCell className="input-invoice-usage-table-cell input-invoice-usage-table-cell--strong-separator" columnRole="identity">
                    {bank ? (
                      <>
                        <ExpandableCellText
                          text={bank.counterpartyName}
                          expanded={bankNameCellExpanded}
                          onToggle={() => onToggleCellExpand(row.id, "bank-name")}
                        />
                        <div className="input-invoice-usage-tag-row">
                          <Tag>{bank.tradeTime ? formatDateTimeText(bank.tradeTime) : "交易日期为空"}</Tag>
                          {bank.detailAvailable && !bankRelationTarget ? (
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
                  </FinanceTableCell>
                  <FinanceTableCell className="input-invoice-usage-table-cell input-invoice-usage-table-cell--amount input-invoice-usage-table-cell--separator" columnRole="amount">
                    {bank ? (
                      <>
                        <div className="input-invoice-usage-bank-amount-line">
                          <span className="input-invoice-usage-money-primary">{formatMoney(bank.amount)}</span>
                          {bankRelationTarget ? (
                            <RelationCountButton
                              extraCount={bankExtraCount}
                              label={`查看${bank.counterpartyName || "该发票"}关联流水 ${row.bank.relationCount} 条`}
                              onClick={() => onOpenDetail(bankRelationTarget)}
                            />
                          ) : null}
                        </div>
                        <div className="input-invoice-usage-bank-tag-row">
                          <Tag tone="info">{directionLabel(bank.directionLabel || bank.direction)}</Tag>
                          <Tag className="input-invoice-usage-bank-tag">
                            {bankAccountLabel(bank) || "银行账户为空"}
                          </Tag>
                        </div>
                      </>
                    ) : <EmptyCell />}
                  </FinanceTableCell>
                  <FinanceTableCell className="input-invoice-usage-table-cell input-invoice-usage-table-cell--separator" columnRole="description">
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
                  </FinanceTableCell>
                </FinanceTableRow>
              );
            })}
          </FinanceTableBody>
      </FinanceTable>
    </div>
  );
}

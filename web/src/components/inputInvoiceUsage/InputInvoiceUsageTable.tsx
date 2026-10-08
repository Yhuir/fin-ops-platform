import { ArrowUpDown, Filter, Info } from "lucide-react";
import { Button, Checkbox, ListBox, PopoverContent, PopoverDialog, PopoverRoot, PopoverTrigger, Select } from "@heroui/react";
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
import BankAccountValue from "../BankAccountValue";
import type { InputInvoiceUsageFilterValue } from "./InputInvoiceUsageFilterMenu";
import { FinanceStatusTag } from "../common/FinanceTable";

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

function OaRelationFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  return <PopoverRoot isOpen={open} onOpenChange={setOpen}>
    <PopoverTrigger aria-label="OA 关联筛选" aria-expanded={open}
      className={`input-invoice-usage-filter-menu__trigger${value !== "all" ? " input-invoice-usage-filter-menu__trigger--active" : ""}`}>
      <span>OA</span><Filter aria-hidden="true" size={14} />
    </PopoverTrigger>
    {open ? <PopoverContent placement="bottom start" className="input-invoice-usage-filter-menu__popover">
      <PopoverDialog aria-label="OA 关联筛选" className="input-invoice-usage-filter-menu__dialog">
        <div role="menu" aria-label="OA 关联">
          {[{ id: "all", label: "全部" }, { id: "linked", label: "已关联 OA" }, { id: "unlinked", label: "未关联 OA" }].map(option =>
            <button key={option.id} type="button" role="menuitemradio" aria-checked={value === option.id}
              className="input-invoice-usage-filter-menu__item" onClick={() => { onChange(option.id); setOpen(false); }}>{option.label}</button>)}
        </div>
      </PopoverDialog>
    </PopoverContent> : null}
  </PopoverRoot>;
}

const PAGE_SIZE_OPTIONS = [20, 50, 100];

type TagTone = "neutral" | "warning" | "info" | "success";

const paymentStatusToneByCode: Record<string, TagTone> = {
  paid: "success",
  waiting_payment: "warning",
  unclassified: "neutral",
  cash_turnover: "info",
  offset: "info",
};

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

function paymentStatusTone(code: string): TagTone {
  return paymentStatusToneByCode[code] ?? "neutral";
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

function bankAccountLabel(bank: InputInvoiceUsageRow["bank"]["primary"]) {
  if (!bank) {
    return "";
  }
  if (bank.bankShortName) {
    return [bank.bankShortName, bank.accountLast4].filter(Boolean).join(" ");
  }
  return bank.bankAccount || [bank.bankName, bank.accountLast4].filter(Boolean).join(" ");
}

function HeaderCell({
  label,
  align = "left",
  separated,
  strongSeparated,
  emphasized,
  rowSpan,
}: {
  label: ReactNode;
  align?: "left" | "right" | "center";
  separated?: boolean;
  strongSeparated?: boolean;
  emphasized?: boolean;
  rowSpan?: number;
}) {
  return (
    <th
      className={classNames(
        "finance-table__column",
        "input-invoice-usage-table-sub-header",
        align && `input-invoice-usage-table-sub-header--${align}`,
        separated && "input-invoice-usage-table-cell--separator",
        strongSeparated && "input-invoice-usage-table-cell--strong-separator",
      )}
      data-column-role={align === "right" ? "amount" : emphasized ? "status" : "description"}
      rowSpan={rowSpan}
      scope="col"
    >
      <span className="input-invoice-usage-table-header-stack">{label}</span>
    </th>
  );
}

function SortHeaderButton({
  label,
  active,
  direction,
  onClick,
}: {
  label: string;
  active: boolean;
  direction: InputInvoiceUsageSortDirection | "";
  onClick: () => void;
}) {
  const stateLabel = active && direction ? (direction === "asc" ? "升序" : "降序") : "未排序";
  return (
    <button
      aria-label={`按${label}排序`}
      className={classNames("input-invoice-usage-sort-button", active && "input-invoice-usage-sort-button--active")}
      onClick={onClick}
      title={`${label}${stateLabel}`}
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
}: {
  children: ReactNode;
  tone?: TagTone;
}) {
  return (
    <span className={classNames("input-invoice-usage-tag", `input-invoice-usage-tag--${tone}`)}>
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
  totalCount,
  onClick,
}: {
  label: string;
  totalCount: number;
  onClick: () => void;
}) {
  if (totalCount <= 1) {
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
      {`+${totalCount}`}
    </button>
  );
}

function relationCount(relationCount: number | undefined): number {
  return Math.max(0, Number(relationCount ?? 0));
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
      <div className="finance-table finance-table--contained finance-table--selectable-text input-invoice-usage-table input-invoice-usage-table-shell">
        <div className="finance-table__scroll" ref={tableWrapRef}>
          <table aria-label="进项发票使用情况表" className="finance-table__content">
            <colgroup>
              <col className="input-invoice-usage-col--invoice" />
              <col className="input-invoice-usage-col--seller" />
              <col className="input-invoice-usage-col--invoice-amount" />
              <col className="input-invoice-usage-col--business" />
            </colgroup>
            <colgroup>
              <col className="input-invoice-usage-col--payment" />
            </colgroup>
            <colgroup>
              <col className="input-invoice-usage-col--oa" />
              <col className="input-invoice-usage-col--project" />
            </colgroup>
            <colgroup>
              <col className="input-invoice-usage-col--counterparty" />
              <col className="input-invoice-usage-col--bank-amount" />
              <col className="input-invoice-usage-col--remark" />
            </colgroup>
            <thead className="input-invoice-usage-table-head">
              <tr>
                <th className="input-invoice-usage-table-group-header" colSpan={4} scope="colgroup">进项发票</th>
                <HeaderCell align="center" label="支付状态" rowSpan={2} strongSeparated emphasized />
                <th className="input-invoice-usage-table-group-header input-invoice-usage-table-cell--strong-separator" colSpan={2} scope="colgroup">
                  <OaRelationFilter value={selectedValues(filters.find(item => item.field === "oa_relation"))[0] ?? "all"}
                    onChange={key => key === "all" ? onFilterClear("oa_relation") : onFilterApply({ field: "oa_relation", operator: "in", values: [key] })} />
                </th>
                <th className="input-invoice-usage-table-group-header input-invoice-usage-table-cell--strong-separator" colSpan={3} scope="colgroup">流水</th>
              </tr>
              <tr>
                <HeaderCell
                  label={(
                    <span className="input-invoice-usage-table-column-heading"><span>发票号码</span><SortHeaderButton active={sortField === "invoice_date"} direction={sortField === "invoice_date" ? sortDirection : ""} label="开票日期" onClick={() => onSortChange("invoice_date")} /></span>
                  )}
                />
                <HeaderCell label={filterMenu("seller_name", "销方名称")} separated />
                <HeaderCell
                  align="right"
                  label="价税合计/税率"
                  separated
                />
                <HeaderCell label="货物或应税劳务名称" separated />
                <HeaderCell
                  label={(
                    <CompositeFilterMenu
                      columns={[
                        { field: "oa_applicant", label: "OA申请人", options: filterOptions.oa_applicant ?? [] },
                        { field: "oa_application_type", label: "类型", options: filterOptions.oa_application_type ?? [] },
                      ]}
                      currentFilters={filters}
                      label="申请人/类型"
                      onApply={onFilterApply}
                      onClear={onFilterClear}
                    />
                  )}
                  strongSeparated
                />
                <HeaderCell label={filterMenu("oa_project_name", "项目名称")} separated />
                <HeaderCell label={filterMenu("bank_counterparty_name", "对方户名")} strongSeparated />
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
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr className="finance-table__row" id="input-invoice-usage-empty">
                  <td className="finance-table__cell input-invoice-usage-table-state-cell" colSpan={10}>{emptyStateMessage}</td>
                </tr>
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
                const oaTotalCount = relationCount(row.oa.relationCount);
                const bankTotalCount = relationCount(row.bank.originalTransactionCount);
                const invoiceTotalCount = relationCount(row.invoiceRelations.relationCount);

                return (
                  <tr className="finance-table__row input-invoice-usage-table-row" id={row.id} key={row.id}>
                    <th className="finance-table__cell input-invoice-usage-table-cell" data-column-role="identity" scope="row">
                      <div className="input-invoice-usage-inline-row">
                        <span className="input-invoice-usage-cell-primary" title={invoiceNo}>{invoiceNo}</span>
                        <DetailButton
                          iconOnly
                          label={`查看发票 ${invoiceNo} 详情`}
                          onClick={() => onOpenDetail({ kind: "invoice", id: row.invoice.id, rowId: row.id })}
                        />
                        {invoiceRelationTarget ? (
                          <RelationCountButton
                            totalCount={invoiceTotalCount}
                            label={`查看发票 ${invoiceNo} 关联发票 ${row.invoiceRelations.relationCount} 张`}
                            onClick={() => onOpenDetail(invoiceRelationTarget)}
                          />
                        ) : null}
                      </div>
                      <div className="input-invoice-usage-tag-row">
                        <Tag>{dateOnly(row.invoice.issueDate)}</Tag>
                      </div>
                    </th>
                    <td className="finance-table__cell input-invoice-usage-table-cell input-invoice-usage-table-cell--separator" data-column-role="identity">
                      <div className="input-invoice-usage-cell-primary">{row.invoice.sellerName || "-"}</div>
                      <div className="input-invoice-usage-cell-secondary">{row.invoice.sellerTaxNo || "-"}</div>
                    </td>
                    <td className="finance-table__cell input-invoice-usage-table-cell input-invoice-usage-table-cell--amount input-invoice-usage-table-cell--separator" data-column-role="amount">
                      <div className="input-invoice-usage-money-primary input-invoice-usage-invoice-total">{formatMoney(row.invoice.totalWithTax, "—")}</div>
                      <div className="input-invoice-usage-cell-secondary input-invoice-usage-tax-rate">{row.invoice.taxRate}</div>
                    </td>
                    <td className="finance-table__cell input-invoice-usage-table-cell input-invoice-usage-table-cell--separator" data-column-role="description">
                      <ExpandableCellText
                        text={row.invoice.taxableItemName}
                        expanded={invoiceCellExpanded}
                        onToggle={() => onToggleCellExpand(row.id, "invoice-business")}
                      />
                    </td>
                    <td className="finance-table__cell input-invoice-usage-table-cell input-invoice-usage-table-cell--strong-separator input-invoice-usage-payment-cell" data-column-role="status">
                      <Tag tone={paymentStatusTone(row.paymentStatus.code)}>{row.paymentStatus.label}</Tag>
                      {row.paymentStatus.code === "unclassified" ? <div className="input-invoice-usage-cell-secondary">{row.paymentStatus.reason}</div> : null}
                    </td>
                    <td className="finance-table__cell input-invoice-usage-table-cell input-invoice-usage-table-cell--strong-separator" data-column-role="identity">
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
                                totalCount={oaTotalCount}
                                label={`查看${oa.applicant || "该发票"}关联OA ${row.oa.relationCount} 条`}
                                onClick={() => onOpenDetail(oaRelationTarget)}
                              />
                            ) : null}
                          </div>
                          <div className="input-invoice-usage-tag-row">
                            <FinanceStatusTag>{oa.applicationType || "类型为空"}</FinanceStatusTag>
                            {row.oa.hasMultiple && oa.amount ? (
                              <Tag tone="info">{`合计 ${formatMoney(oa.amount)}`}</Tag>
                            ) : null}
                          </div>
                        </>
                      ) : <EmptyCell />}
                    </td>
                    <td className="finance-table__cell input-invoice-usage-table-cell input-invoice-usage-table-cell--separator" data-column-role="description">
                      {oa ? (
                        <ExpandableCellText
                          text={oa.projectName}
                          expanded={projectCellExpanded}
                          onToggle={() => onToggleCellExpand(row.id, "oa-project")}
                        />
                      ) : <EmptyCell />}
                    </td>
                    <td className="finance-table__cell input-invoice-usage-table-cell input-invoice-usage-table-cell--strong-separator" data-column-role="identity">
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
                    </td>
                    <td className="finance-table__cell input-invoice-usage-table-cell input-invoice-usage-table-cell--amount input-invoice-usage-table-cell--separator" data-column-role="amount">
                      {bank ? (
                        <>
                          <div className="input-invoice-usage-bank-amount-line">
                            <span className="input-invoice-usage-money-primary">{formatMoney(row.bank.netAmount, "—")}</span>
                            {bankRelationTarget ? (
                              <RelationCountButton
                                totalCount={bankTotalCount}
                                label={`查看${bank.counterpartyName || "该发票"}关联流水 ${row.bank.originalTransactionCount} 条`}
                                onClick={() => onOpenDetail(bankRelationTarget)}
                              />
                            ) : null}
                          </div>
                          <div className="input-invoice-usage-bank-tag-row">
                            <Tag tone="info">{row.bank.netDirectionLabel}</Tag>
                            <BankAccountValue value={bankAccountLabel(bank) || "—"} />
                          </div>
                        </>
                      ) : <EmptyCell />}
                    </td>
                    <td className="finance-table__cell input-invoice-usage-table-cell input-invoice-usage-table-cell--separator" data-column-role="description">
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
        <div className="finance-table__footer">
          <div className="input-invoice-usage-pagination">
            <Select aria-label="每页行数" className="input-invoice-usage-pagination-size" onChange={(key) => onPageSizeChange(Number(key))} value={String(pageSize)}>
              <Select.Trigger><Select.Value /></Select.Trigger>
              <Select.Popover><ListBox>{PAGE_SIZE_OPTIONS.map((option) => <ListBox.Item id={String(option)} key={option} textValue={String(option)}>{option}</ListBox.Item>)}</ListBox></Select.Popover>
            </Select>
            <Button size="sm" variant="secondary" isDisabled={page <= 1} onPress={() => onPageChange(page - 1)}>上一页</Button>
            <span>第 {page} / {Math.max(1, Math.ceil(total / pageSize))} 页</span>
            <Button size="sm" variant="secondary" isDisabled={page * pageSize >= total} onPress={() => onPageChange(page + 1)}>下一页</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

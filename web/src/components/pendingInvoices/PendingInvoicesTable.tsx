import { Fragment } from "react";
import { RelationCountButton } from "../common/RelationCountButton";
import RelationRowsMotion from "../common/RelationRowsMotion";
import { useRelationExpansion, useRelationRowExpansion } from "../../hooks/useRelationExpansion";
import { pendingInvoiceDisplayRows, pendingInvoiceMembers, type PendingInvoiceDisplayRow } from "../../features/pendingInvoices/relationExpansion";
import { formatDateTimeText } from "../../features/dateTime";
import BankSplitChips from "../../features/bankSplits/BankSplitChips";
import { Button, Checkbox, ListBox, Select } from "@heroui/react";
import { Filter, Info } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { createPortal } from "react-dom";

import {
  AmountCell,
  EmptyValue,
  FinanceDirectionTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTablePagination,
  FinanceTableRow,
  FinanceStatusTag,
  type FinanceTone,
} from "../common/FinanceTable";
import { formatMoney } from "../../features/money";
import OaWorkflowStatusChip from "../common/OaWorkflowStatusChip";
import type {
  PendingInvoiceDirection,
  PendingInvoiceColumnFilter,
  PendingInvoiceFilterField,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceRow,
  PendingInvoiceSortDirection,
  PendingInvoiceSortField,
  PendingInvoiceStatusSeverity,
} from "../../features/pendingInvoices/types";

export type PendingInvoicesTableConfig = {
  sortField: PendingInvoiceSortField;
  sortDirection: PendingInvoiceSortDirection;
};

type PendingInvoicesTableProps = {
  rows: PendingInvoiceRow[];
  config: PendingInvoicesTableConfig;
  onSortChange: (field: PendingInvoiceSortField, direction?: PendingInvoiceSortDirection) => void;
  onOpenObjectDetail: (target: PendingInvoiceObjectDetailTarget) => void;
  direction: PendingInvoiceDirection;
  statusFilterControl: ReactNode;
  filterFields: PendingInvoiceFilterField[];
  columnFilters: PendingInvoiceColumnFilter[];
  onApplyColumnFilters: (filters: PendingInvoiceColumnFilter[]) => void;
  onClearColumnFilters: (fields: string[]) => void;
  selectedTransactionIds?: Set<string>;
  onToggleTransactionSelection?: (row: PendingInvoiceRow) => void;
  isTransactionSelectable?: (row: PendingInvoiceRow) => boolean;
  emptyStateMessage?: string;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
};

function invoiceNumber(row: NonNullable<PendingInvoiceRow["inputInvoices"]["primary"]>) {
  return row.digitalInvoiceNo || [row.invoiceCode, row.invoiceNo].filter(Boolean).join(" ") || row.invoiceNo || "-";
}

function bankAccountLabel(row: PendingInvoiceRow["bankTransaction"]) {
  return [row.bankShortName || row.bankName, row.accountLast4].filter(Boolean).join(" ") || "-";
}

function numericAmount(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function rowMoneyDirection(bank: PendingInvoiceRow["bankTransaction"], direction: PendingInvoiceDirection) {
  if (direction === "income") {
    return "income";
  }
  if (direction === "expense") {
    return "expense";
  }
  return numericAmount(bank.creditAmount) > 0 && numericAmount(bank.debitAmount) <= 0 ? "income" : "expense";
}

function tagPathLabel(row: PendingInvoiceRow["bankTransaction"]) {
  const path = row.effectiveTagLabelPath.map((item) => item.trim()).filter(Boolean);
  if (path.length > 0) {
    return path.join(" / ");
  }
  return [row.effectiveTagPrimaryLabel, row.effectiveTagSubLabel]
    .map((item) => item?.trim())
    .filter(Boolean)
    .join(" / ") || row.effectiveTagLabel || row.effectiveTagCode || "未标注";
}

function severityTone(severity: PendingInvoiceStatusSeverity): FinanceTone {
  switch (severity) {
    case "success":
      return "success";
    case "warning":
      return "warning";
    case "error":
      return "danger";
    case "info":
      return "info";
    default:
      return "neutral";
  }
}

function cx(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

type ColumnFilterGroup = {
  label: string;
  fields: Array<{ field: string; label: string }>;
};

function sortableHeader({
  label,
  sortDirection,
  onSort,
  filterMenu,
}: {
  label: string;
  sortDirection?: "ascending" | "descending";
  onSort?: () => void;
  filterMenu?: ReactNode;
}) {
  return (
    <span className="pending-invoices-header-control">
      <button
        aria-label={`排序 ${label}`}
        className="pending-invoices-sort-button"
        data-sort-direction={sortDirection}
        disabled={!onSort}
        onClick={onSort}
        type="button"
      >
        <span>{label}</span>
        <span aria-hidden="true" className="pending-invoices-sort-icon">
          {sortDirection ? (sortDirection === "ascending" ? "↑" : "↓") : "↕"}
        </span>
      </button>
      {filterMenu}
    </span>
  );
}

function selectedValues(filters: PendingInvoiceColumnFilter[], field: string) {
  const filter = filters.find((item) => item.field === field && item.operator === "in");
  return "values" in (filter ?? {}) ? new Set((filter as { values?: string[] }).values ?? []) : new Set<string>();
}

function optionsForField(fields: PendingInvoiceFilterField[], field: string) {
  return fields.find((item) => item.field === field)?.options ?? [];
}

function ColumnFilterMenu({
  group,
  filterFields,
  columnFilters,
  onApply,
  onClear,
}: {
  group: ColumnFilterGroup;
  filterFields: PendingInvoiceFilterField[];
  columnFilters: PendingInvoiceColumnFilter[];
  onApply: (filters: PendingInvoiceColumnFilter[]) => void;
  onClear: (fields: string[]) => void;
}) {
  const popoverWidth = 268;
  const containerRef = useRef<HTMLSpanElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [popoverStyle, setPopoverStyle] = useState<{ top: number; left: number; maxHeight: number } | null>(null);
  const [draft, setDraft] = useState<Record<string, Set<string>>>(() => Object.fromEntries(
    group.fields.map((field) => [field.field, selectedValues(columnFilters, field.field)]),
  ));
  const fields = group.fields.map((field) => ({
    ...field,
    options: optionsForField(filterFields, field.field),
  }));

  function resetDraftFromFilters() {
    setDraft(Object.fromEntries(group.fields.map((field) => [field.field, selectedValues(columnFilters, field.field)])));
  }

  function itemKey(field: string, value: string) {
    return `${field}::${value}`;
  }

  function toggleDraftValue(field: string, value: string) {
    setDraft((current) => {
      const nextValues = new Set(current[field] ?? []);
      if (nextValues.has(value)) {
        nextValues.delete(value);
      } else {
        nextValues.add(value);
      }
      return { ...current, [field]: nextValues };
    });
  }

  function applyDraft() {
    onClear(group.fields.map((field) => field.field));
    onApply(group.fields.flatMap((field) => {
      const values = [...(draft[field.field] ?? new Set<string>())];
      return values.length > 0 ? [{ field: field.field, operator: "in" as const, values }] : [];
    }) as PendingInvoiceColumnFilter[]);
    setOpen(false);
  }

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) {
      return;
    }

    const updatePosition = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      const viewportInset = 8;
      const maxLeft = Math.max(viewportInset, window.innerWidth - popoverWidth - viewportInset);
      const belowTop = rect.bottom + 6;
      const belowAvailable = window.innerHeight - belowTop - viewportInset;
      const aboveAvailable = rect.top - viewportInset * 2;
      const shouldOpenAbove = belowAvailable < 180 && aboveAvailable > belowAvailable;
      const availableHeight = shouldOpenAbove ? aboveAvailable : belowAvailable;
      const maxHeight = Math.max(160, Math.min(360, availableHeight));
      setPopoverStyle({
        top: shouldOpenAbove ? Math.max(viewportInset, rect.top - 6 - maxHeight) : belowTop,
        left: Math.min(Math.max(viewportInset, rect.right - popoverWidth), maxLeft),
        maxHeight,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!containerRef.current?.contains(target) && !popoverRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const active = group.fields.some((field) => selectedValues(columnFilters, field.field).size > 0);
  return (
    <span ref={containerRef} className="pending-invoices-column-filter">
      <Button
        ref={buttonRef}
        isIconOnly
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`筛选 ${group.label}`}
        className={cx("pending-invoices-column-filter-button", active && "pending-invoices-column-filter-button--active")}
        onPress={() => {
          setOpen((current) => {
            if (!current) {
              resetDraftFromFilters();
            }
            return !current;
          });
        }}
        size="sm"
        variant="ghost"
      >
        <Filter aria-hidden="true" size={13} strokeWidth={2.4} />
      </Button>
      {open && popoverStyle ? createPortal(
        <div
          ref={popoverRef}
          aria-label={`${group.label}筛选`}
          className="pending-invoices-column-filter-popover"
          role="menu"
          style={{
            top: `${popoverStyle.top}px`,
            left: `${popoverStyle.left}px`,
            maxHeight: `${popoverStyle.maxHeight}px`,
          }}
        >
          <div className="pending-invoices-column-filter-menu">
            {fields.map((field) => (
              <div className="pending-invoices-column-filter-menu__group" key={field.field} role="group" aria-label={field.label}>
                <div className="pending-invoices-column-filter-menu__label">{field.label}</div>
                {field.options.length === 0 ? <div className="pending-invoices-column-filter-menu__empty">暂无选项</div> : null}
                {field.options.map((option) => {
                  const selected = draft[field.field]?.has(option.value) ?? false;
                  return (
                    <button
                      aria-checked={selected}
                      aria-label={`${field.label}：${option.label} ${option.count}`}
                      className="pending-invoices-column-filter-menu__option"
                      key={itemKey(field.field, option.value)}
                      onClick={() => toggleDraftValue(field.field, option.value)}
                      role="menuitemcheckbox"
                      type="button"
                    >
                      <span>{field.label}：{option.label}</span>
                      <span>{option.count}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
          <div className="pending-invoices-column-filter-menu__actions">
            <Button
              className="pending-invoices-column-filter-menu__clear"
              onPress={() => {
                onClear(group.fields.map((field) => field.field));
                setOpen(false);
              }}
              size="sm"
              variant="outline"
            >
              清除
            </Button>
            <Button
              className="pending-invoices-column-filter-menu__apply"
              onPress={applyDraft}
              size="sm"
            >
              应用筛选
            </Button>
          </div>
        </div>,
        document.body,
      ) : null}
    </span>
  );
}

export default function PendingInvoicesTable({
  rows,
  config,
  onSortChange,
  onOpenObjectDetail,
  direction,
  statusFilterControl,
  filterFields,
  columnFilters,
  onApplyColumnFilters,
  onClearColumnFilters,
  selectedTransactionIds,
  onToggleTransactionSelection,
  isTransactionSelectable,
  emptyStateMessage = "当前条件下没有待找发票流水。",
  tableWrapRef,
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: PendingInvoicesTableProps) {
  const expansion = useRelationExpansion(rows);
  const bankGroupLabel = direction === "income" ? "收入流水" : direction === "all" ? "流水" : "支出流水";
  const invoiceGroupLabel = direction === "income" ? "销项发票" : direction === "all" ? "发票" : "进项发票";
  const invoicePartyLabel = direction === "income" ? "购方 / 识别号" : "供应商 / 识别号";
  const counterpartyFilter: ColumnFilterGroup = {
    label: "对方户名",
    fields: [
      { field: "counterparty_name", label: "对方户名" },
      { field: "transaction_tag", label: "流水标签" },
    ],
  };
  const amountFilter: ColumnFilterGroup = {
    label: "金额 / 银行账户",
    fields: [
      { field: "bank_account", label: "银行账户" },
      { field: "direction", label: "收支" },
    ],
  };
  const invoicePartyFilter: ColumnFilterGroup = {
    label: invoicePartyLabel,
    fields: [{ field: "seller_name", label: direction === "income" ? "购方" : "供应商" }],
  };
  const oaFilter: ColumnFilterGroup = {
    label: "申请人 / 类型",
    fields: [
      { field: "oa_applicant", label: "申请人" },
      { field: "oa_application_type", label: "类型" },
    ],
  };
  const projectFilter: ColumnFilterGroup = {
    label: "项目",
    fields: [{ field: "project_name", label: "项目" }],
  };
  function sortDirectionFor(field: PendingInvoiceSortField) {
    return config.sortField === field ? (config.sortDirection === "asc" ? "ascending" : "descending") : undefined;
  }

  function handleNativeSort(field: PendingInvoiceSortField) {
    const nextDirection = config.sortField === field && config.sortDirection === "asc" ? "desc" : "asc";
    onSortChange(field, nextDirection);
  }

  function renderSortableHeader(field: PendingInvoiceSortField, label: string, filterMenu?: ReactNode) {
    return sortableHeader({
      label,
      sortDirection: sortDirectionFor(field),
      onSort: () => handleNativeSort(field),
      filterMenu,
    });
  }

  return (
    <div className="finance-page-table-frame pending-invoices-table-frame">
      <FinanceTable
        ariaLabel="待找发票四区表"
        className="pending-invoices-table pending-invoices-table-shell"
        footer={(
          <div className="pending-invoices-pagination">
            <Select aria-label="每页行数" onSelectionChange={(key) => onPageSizeChange(Number(key))} selectedKey={String(pageSize)}>
              <Select.Trigger className="pending-invoices-pagination-size">
                <Select.Value />
                <Select.Indicator />
              </Select.Trigger>
              <Select.Popover>
                <ListBox>
                  {[25, 50, 100].map((option) => (
                    <ListBox.Item id={String(option)} key={option} textValue={`${option} 行/页`}>
                      {option} 行/页
                    </ListBox.Item>
                  ))}
                </ListBox>
              </Select.Popover>
            </Select>
            <FinanceTablePagination className="finance-table-pagination--fit" compact onPageChange={onPageChange} page={page} pageSize={pageSize} total={total} />
          </div>
        )}
        header={<div className="pending-invoices-group-headings" aria-label="表格分组">
          <div className="pending-invoices-group-heading pending-invoices-group-heading--bank">{bankGroupLabel}</div>
          <div className="pending-invoices-group-heading pending-invoices-group-heading--status">发票获取状态</div>
          <div className="pending-invoices-group-heading pending-invoices-group-heading--invoice">{invoiceGroupLabel}</div>
          <div className="pending-invoices-group-heading pending-invoices-group-heading--oa">OA</div>
        </div>}
        minWidth={1380}
        selectableText
        scrollMode="contained"
        scrollRef={tableWrapRef}
      >
            <FinanceTableHeader>
                <FinanceTableColumn className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-col-counterparty" columnRole="identity" id="counterparty_name" isRowHeader>
                  {renderSortableHeader("counterparty_name", "对方户名", <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={counterpartyFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </FinanceTableColumn>
                <FinanceTableColumn className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-table-cell--amount pending-invoices-col-amount" columnRole="amount" id="amount">
                  {renderSortableHeader("amount", "金额 / 银行账户", <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={amountFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </FinanceTableColumn>
                <FinanceTableColumn className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-col-summary" columnRole="description" id="summary">摘要 / 凭证</FinanceTableColumn>
                <FinanceTableColumn className="pending-invoices-table-sub-header pending-invoices-table-sub-header--status pending-invoices-table-cell--left-border pending-invoices-col-status" columnRole="status" id="invoice_status">
                  <span className="pending-invoices-status-filter-cell">{statusFilterControl}</span>
                </FinanceTableColumn>
                <FinanceTableColumn className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-table-cell--left-border pending-invoices-col-invoice-no" columnRole="identity" id="trade_date">
                  {renderSortableHeader("trade_date", "发票号码 / 开票日期")}
                </FinanceTableColumn>
                <FinanceTableColumn className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-col-seller" columnRole="identity" id="seller_name">
                  {renderSortableHeader("seller_name", invoicePartyLabel, <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={invoicePartyFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </FinanceTableColumn>
                <FinanceTableColumn className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-table-cell--amount pending-invoices-col-invoice-amount" columnRole="amount" id="invoice_total">
                  {renderSortableHeader("invoice_total", "金额")}
                </FinanceTableColumn>
                <FinanceTableColumn className="pending-invoices-table-sub-header pending-invoices-table-sub-header--oa pending-invoices-table-cell--left-border pending-invoices-col-oa-applicant" columnRole="identity" id="oa_applicant">
                  {renderSortableHeader("oa_applicant", "申请人 / 类型", <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={oaFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </FinanceTableColumn>
                <FinanceTableColumn className="pending-invoices-table-sub-header pending-invoices-table-sub-header--oa pending-invoices-col-oa-project" columnRole="description" id="project_name">
                  {renderSortableHeader("project_name", "项目", <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={projectFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </FinanceTableColumn>
            </FinanceTableHeader>
            <FinanceTableBody>
              {rows.length === 0 ? (
                <FinanceTableRow id="pending-invoices-empty">
                  <FinanceTableCell className="pending-invoices-table-state-cell" columnRole="identity">{emptyStateMessage}</FinanceTableCell>
                  {Array.from({ length: 8 }, (_, index) => <FinanceTableCell columnRole="description" key={index}><EmptyValue /></FinanceTableCell>)}
                </FinanceTableRow>
              ) : rows.map((row) => (
                <PendingInvoiceTableRow
                  direction={direction}
                  key={row.id}
                  onOpenObjectDetail={onOpenObjectDetail}
                  expansion={expansion}
                  onToggleTransactionSelection={onToggleTransactionSelection}
                  row={row}
                  selectedTransactionIds={selectedTransactionIds}
                  isTransactionSelectable={isTransactionSelectable}
                />
              ))}
            </FinanceTableBody>
      </FinanceTable>
    </div>
  );
}

function TextCell({ primary, secondary, title }: { primary: ReactNode; secondary?: ReactNode; title?: string }) {
  return (
    <span className="pending-invoices-cell-stack">
      <span className="pending-invoices-cell-primary" title={title}>{primary}</span>
      {secondary ? <span className="pending-invoices-cell-secondary">{secondary}</span> : null}
    </span>
  );
}

function DetailButton({
  children,
  disabled,
  label,
  onClick,
}: {
  children: ReactNode;
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      className="pending-invoices-inline-action"
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  );
}

function PendingInvoiceTableRow({
  expansion,
  row,
  direction,
  onOpenObjectDetail,
  selectedTransactionIds,
  onToggleTransactionSelection,
  isTransactionSelectable,
}: Omit<PendingInvoicesTableProps, "rows" | "config" | "onSortChange" | "statusFilterControl" | "filterFields" | "columnFilters" | "onApplyColumnFilters" | "onClearColumnFilters" | "page" | "pageSize" | "total" | "onPageChange" | "onPageSizeChange"> & { row: PendingInvoiceRow; expansion: ReturnType<typeof useRelationExpansion> }) {
  const presence = useRelationRowExpansion(row.id, expansion);
  const members = pendingInvoiceMembers(row);
  const displayRows = pendingInvoiceDisplayRows(row, presence.view ?? 'bank', members);
  const counts = { bank: members.bank.length, invoice: row.inputInvoices.relationCount, oa: row.oa.relationCount };
  const transactionId = row.bankTransaction.id || row.id;
  const transactionSelectable = isTransactionSelectable?.(row) === true;
  const transactionSelected = selectedTransactionIds?.has(transactionId) === true;
  const complete = (members.bank.length === 1 && !row.bankTransactions.hasMultiple
    || row.bankTransactions.originalTransactionCount === members.bank.length)
    && row.inputInvoices.relationCount === members.invoice.length && row.oa.relationCount === members.oa.length
    && Object.values(members).every(items => items.every(item => Boolean(item.id))
      && new Set(items.map(item => item.id)).size === items.length);
  if (!complete) return <FinanceTableRow id={row.id} className="pending-invoices-table-row">
    <FinanceTableCell columnRole="identity"><span role="alert">关系摘要不完整</span></FinanceTableCell>
    {Array.from({ length: 8 }, (_, index) => <FinanceTableCell columnRole="description" key={index}><EmptyValue /></FinanceTableCell>)}
  </FinanceTableRow>;
  const renderRow = (display: PendingInvoiceDisplayRow, index: number) => {
    const bank = display.bank;
    const primaryInvoice = display.invoice;
    const primaryOa = display.oa;
    const invoiceNumberLabel = primaryInvoice ? invoiceNumber(primaryInvoice) : '';
    const counterpartyLabel = bank?.counterpartyName || '';
    const moneyDirection = bank ? rowMoneyDirection(bank, direction) : direction === 'income' ? 'income' : 'expense';
    const countButton = (kind: 'bank' | 'invoice' | 'oa') => index === 0 && counts[kind] > 1
      ? <RelationCountButton kind={kind} count={counts[kind]} expanded={expansion.rowId === row.id && expansion.view === kind && expansion.expanded} onClick={() => expansion.toggle(row.id, kind)} />
      : null;
    return <FinanceTableRow className="pending-invoices-table-row" dataRelationGroup={presence.view ? row.id : undefined} id={index === 0 ? row.id : `${row.id}:${presence.view}:${display.id}`} key={`${presence.view}:${display.id}`}>
      <FinanceTableCell className="pending-invoices-table-cell pending-invoices-col-counterparty" columnRole="identity">
        <span className="pending-invoices-counterparty-cell pending-invoices-counterparty-cell--selectable">
          <span className="pending-invoices-row-select-slot">
            {index === 0 && transactionSelectable ? <Checkbox aria-label={`选择流水 ${row.bankTransaction.counterpartyName || "未知对方"}`} className="pending-invoices-row-select" isSelected={transactionSelected} onChange={() => onToggleTransactionSelection?.(row)} /> : null}
          </span>
          <span className="pending-invoices-counterparty-content">
            <span className="pending-invoices-counterparty-row">
              <span className="pending-invoices-counterparty-name" title={counterpartyLabel}>{counterpartyLabel || <EmptyValue />}</span>
              {countButton('bank')}
              {bank ? <button aria-label={`流水详情 ${counterpartyLabel}`} className="pending-invoices-icon-button" onClick={() => onOpenObjectDetail({ kind: 'bankTransaction', id: bank.id, rowId: row.id })} title="流水详情" type="button"><Info aria-hidden="true" size={14} strokeWidth={2.3} /></button> : null}
            </span>
            {bank ? <>
              {bank.bankSplitParts?.length ? null : <span className="pending-invoices-tag pending-invoices-tag--neutral" title={tagPathLabel(bank)}>{tagPathLabel(bank)}</span>}
              <span className="pending-invoices-trade-time" aria-label="交易时间">{bank.tradeTime ? formatDateTimeText(bank.tradeTime) : '交易时间未提供'}</span>
            </> : null}
          </span>
        </span>
      </FinanceTableCell>
      <FinanceTableCell className="pending-invoices-table-cell pending-invoices-table-cell--amount pending-invoices-col-amount" columnRole="amount">
        {bank ? <>
          <AmountCell account={bankAccountLabel(bank)} amount={formatMoney(bank.originalAmount, '—')} className="pending-invoices-amount-cell" direction={<FinanceDirectionTag direction={moneyDirection}>{moneyDirection === 'income' ? '收' : '支'}</FinanceDirectionTag>} />
          {bank.bankSplitParts?.length ? <BankSplitChips parts={bank.bankSplitParts} /> : null}
        </> : <EmptyValue />}
      </FinanceTableCell>
      <FinanceTableCell className="pending-invoices-table-cell pending-invoices-table-cell--summary pending-invoices-col-summary" columnRole="description">
        {bank ? <TextCell primary={bank.summary || <EmptyValue />} secondary={bank.remark || bank.voucherNo || <EmptyValue />} title={bank.summary} /> : <EmptyValue />}
      </FinanceTableCell>
      <FinanceTableCell className="pending-invoices-table-cell pending-invoices-table-cell--status pending-invoices-table-cell--left-border pending-invoices-col-status" columnRole="status">
        <span className="pending-invoices-status-cell"><FinanceStatusTag tone={severityTone(row.invoiceAcquisitionStatus.severity)}>{row.invoiceAcquisitionStatus.label}</FinanceStatusTag></span>
      </FinanceTableCell>
      <FinanceTableCell className="pending-invoices-table-cell pending-invoices-table-cell--left-border pending-invoices-col-invoice-no" columnRole="identity">
        {primaryInvoice ? <TextCell primary={<span className="pending-invoices-inline-row">{invoiceNumberLabel}{countButton('invoice')}</span>} secondary={<span className="pending-invoices-inline-row"><span>{primaryInvoice.issueDate || '-'}</span><DetailButton label={`发票详情 ${invoiceNumberLabel}`} onClick={() => onOpenObjectDetail({ kind: 'invoice', id: primaryInvoice.id, rowId: row.id })}><Info aria-hidden="true" size={14} strokeWidth={2.3} /></DetailButton></span>} title={invoiceNumberLabel} /> : countButton('invoice') || <EmptyValue />}
      </FinanceTableCell>
      <FinanceTableCell className="pending-invoices-table-cell pending-invoices-col-seller" columnRole="identity">
        {primaryInvoice ? <TextCell primary={(primaryInvoice.invoiceType === 'output' ? primaryInvoice.buyerName : primaryInvoice.sellerName) || <EmptyValue />} secondary={primaryInvoice.invoiceType === 'output' ? undefined : primaryInvoice.sellerTaxNo || <EmptyValue />} title={primaryInvoice.invoiceType === 'output' ? primaryInvoice.buyerName : primaryInvoice.sellerName} /> : <EmptyValue />}
      </FinanceTableCell>
      <FinanceTableCell className="pending-invoices-table-cell pending-invoices-table-cell--amount pending-invoices-col-invoice-amount" columnRole="amount">
        {primaryInvoice ? <span className="pending-invoices-money-stack"><span className="pending-invoices-money-primary">{formatMoney(primaryInvoice.totalWithTax, '—')}</span></span> : <EmptyValue />}
      </FinanceTableCell>
      <FinanceTableCell className="pending-invoices-table-cell pending-invoices-table-cell--left-border pending-invoices-col-oa-applicant" columnRole="identity">
        {primaryOa ? <TextCell primary={<span className="pending-invoices-inline-row">{primaryOa.applicant || <EmptyValue />}{countButton('oa')}</span>} secondary={<span className="pending-invoices-inline-row"><FinanceStatusTag>{primaryOa.applicationType || '类型为空'}</FinanceStatusTag><OaWorkflowStatusChip status={primaryOa.workflowStatus} /></span>} title={primaryOa.applicant} /> : countButton('oa') || <EmptyValue />}
      </FinanceTableCell>
      <FinanceTableCell className="pending-invoices-table-cell pending-invoices-col-oa-project" columnRole="description">
        {primaryOa ? <TextCell primary={primaryOa.projectName || <EmptyValue />} secondary={<span className="pending-invoices-inline-row"><DetailButton disabled={!primaryOa.detailAvailable} label={`OA详情 ${primaryOa.applicant || primaryOa.id}`} onClick={() => onOpenObjectDetail({ kind: 'oa', id: primaryOa.id, rowId: row.id })}><Info aria-hidden="true" size={14} strokeWidth={2.3} /></DetailButton></span>} title={primaryOa.projectName} /> : <EmptyValue />}
      </FinanceTableCell>
    </FinanceTableRow>;
  };
  return <Fragment>
    {displayRows[0] ? renderRow(displayRows[0], 0) : null}
    {presence.view ? <RelationRowsMotion key={presence.view} expanded={presence.expanded} onExited={presence.onExited}>
      {displayRows.slice(1).map((display, index) => renderRow(display, index + 1))}
    </RelationRowsMotion> : null}
  </Fragment>;
}

import type { Key } from "react";

import { Button, Dropdown, Label, Table, type Selection, type SortDescriptor } from "@heroui/react";
import { Filter, Info, MoreVertical } from "lucide-react";
import { useMemo, useState, type MutableRefObject, type ReactNode } from "react";

import {
  AmountCell,
  EmptyValue,
  FinanceDirectionTag,
  FinanceStatusTag,
  type FinanceTone,
} from "../common/FinanceTable";
import type {
  PendingInvoiceDirection,
  PendingInvoiceColumnFilter,
  PendingInvoiceFilterField,
  PendingInvoiceObjectDetailTarget,
  PendingInvoicePrimaryAction,
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
  onOpenRelation: (row: PendingInvoiceRow) => void;
  onOpenInvoicePicker: (row: PendingInvoiceRow) => void;
  onOpenManualInvoice: (row: PendingInvoiceRow) => void;
  onOpenObjectDetail: (target: PendingInvoiceObjectDetailTarget) => void;
  onMarkIncomeStatus: (row: PendingInvoiceRow, statusCode: "income_no_invoice_required" | "cash_income") => void;
  direction: PendingInvoiceDirection;
  statusFilterControl: ReactNode;
  filterFields: PendingInvoiceFilterField[];
  columnFilters: PendingInvoiceColumnFilter[];
  onApplyColumnFilters: (filters: PendingInvoiceColumnFilter[]) => void;
  onClearColumnFilters: (fields: string[]) => void;
  pendingActionRowIds?: Set<string>;
  selectedTransactionIds?: Set<string>;
  onToggleTransactionSelection?: (row: PendingInvoiceRow) => void;
  isTransactionSelectable?: (row: PendingInvoiceRow) => boolean;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
};

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value || "-";
  }
  return parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

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

function rowMoneyDirection(row: PendingInvoiceRow, direction: PendingInvoiceDirection) {
  if (direction === "income") {
    return "income";
  }
  if (direction === "expense") {
    return "expense";
  }
  return numericAmount(row.bankTransaction.creditAmount) > 0 && numericAmount(row.bankTransaction.debitAmount) <= 0 ? "income" : "expense";
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

const sortableFields = new Set<PendingInvoiceSortField>([
  "trade_date",
  "amount",
  "counterparty_name",
  "seller_name",
  "invoice_total",
  "oa_applicant",
  "project_name",
]);

function isPendingInvoiceSortField(value: Key | null | undefined): value is PendingInvoiceSortField {
  return typeof value === "string" && sortableFields.has(value as PendingInvoiceSortField);
}

function sortableHeader({
  label,
  sortDirection,
  filterMenu,
}: {
  label: string;
  sortDirection?: "ascending" | "descending";
  filterMenu?: ReactNode;
}) {
  return (
    <span className="pending-invoices-header-control">
      <span className="pending-invoices-sort-button" data-sort-direction={sortDirection}>
        <span>{label}</span>
        <span aria-hidden="true" className="pending-invoices-sort-icon">
          {sortDirection ? (sortDirection === "ascending" ? "↑" : "↓") : "↕"}
        </span>
      </span>
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
  const [open, setOpen] = useState(false);
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

  function selectedKeysFromDraft() {
    return new Set(group.fields.flatMap((field) => (
      [...(draft[field.field] ?? new Set<string>())].map((value) => itemKey(field.field, value))
    )));
  }

  function applySelection(keys: Selection) {
    if (keys === "all") {
      return;
    }
    const next: Record<string, Set<string>> = Object.fromEntries(group.fields.map((field) => [field.field, new Set<string>()]));
    for (const key of keys) {
      const rawKey = String(key);
      const [field, ...valueParts] = rawKey.split("::");
      const value = valueParts.join("::");
      if (field in next && value) {
        next[field].add(value);
      }
    }
    setDraft(next);
  }

  function applyDraft() {
    onClear(group.fields.map((field) => field.field));
    onApply(group.fields.flatMap((field) => {
      const values = [...(draft[field.field] ?? new Set<string>())];
      return values.length > 0 ? [{ field: field.field, operator: "in" as const, values }] : [];
    }) as PendingInvoiceColumnFilter[]);
    setOpen(false);
  }

  const active = group.fields.some((field) => selectedValues(columnFilters, field.field).size > 0);
  return (
    <span className="pending-invoices-column-filter">
      <Dropdown
        isOpen={open}
        onOpenChange={(isOpen) => {
          setOpen(isOpen);
          if (isOpen) {
            resetDraftFromFilters();
          }
        }}
      >
        <Button
          isIconOnly
          aria-label={`筛选 ${group.label}`}
          className={cx("pending-invoices-column-filter-button", active && "pending-invoices-column-filter-button--active")}
          size="sm"
          variant="ghost"
        >
          <Filter aria-hidden="true" size={13} strokeWidth={2.4} />
        </Button>
        <Dropdown.Popover isNonModal className="pending-invoices-column-filter-popover" placement="bottom end">
          <Dropdown.Menu
            aria-label={`${group.label}筛选`}
            className="pending-invoices-column-filter-menu"
            selectedKeys={selectedKeysFromDraft()}
            selectionMode="multiple"
            onSelectionChange={applySelection}
          >
          {fields.map((field) => (
              <Dropdown.Section className="pending-invoices-column-filter-menu__group" key={field.field}>
                <Label className="pending-invoices-column-filter-menu__label">{field.label}</Label>
              {field.options.length === 0 ? <div className="pending-invoices-column-filter-menu__empty">暂无选项</div> : null}
                {field.options.map((option) => (
                  <Dropdown.Item
                    className="pending-invoices-column-filter-menu__option"
                    id={itemKey(field.field, option.value)}
                    key={itemKey(field.field, option.value)}
                    textValue={`${field.label}：${option.label} ${option.count}`}
                  >
                    <span>{field.label}：{option.label}</span>
                    <span>{option.count}</span>
                    <Dropdown.ItemIndicator />
                  </Dropdown.Item>
                ))}
              </Dropdown.Section>
          ))}
          </Dropdown.Menu>
          <div className="pending-invoices-column-filter-menu__actions" onClick={(event) => event.stopPropagation()}>
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
        </Dropdown.Popover>
      </Dropdown>
    </span>
  );
}

function shouldOpenRelation(action: PendingInvoicePrimaryAction) {
  return ["view_relation", "view_payment_detail", "view_accumulated", "view_payment_history"].includes(action);
}

function shouldOpenInvoicePicker(action: PendingInvoicePrimaryAction) {
  return ["attach_existing_invoice", "choose_invoice", "select_invoice"].includes(action);
}

function shouldOpenManualInvoice(action: PendingInvoicePrimaryAction) {
  return ["manual_invoice", "create_invoice"].includes(action);
}

function canOpenOaDetail(row: PendingInvoiceRow) {
  const primaryOa = row.oa.primary;
  return Boolean(primaryOa?.id?.startsWith("oa-") && primaryOa.detailAvailable && row.oa.detailAvailable);
}

function RowActionMenu({
  row,
  onOpenRelation,
  onOpenInvoicePicker,
  onOpenManualInvoice,
  onMarkIncomeStatus,
  disabled = false,
}: Pick<PendingInvoicesTableProps, "onOpenRelation" | "onOpenInvoicePicker" | "onOpenManualInvoice" | "onMarkIncomeStatus"> & { row: PendingInvoiceRow; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const action = row.invoiceAcquisitionStatus.primaryAction;
  const prefix = row.bankTransaction.counterpartyName;
  const available = new Set(row.availableActions);
  const canAttach = available.has("attach_existing_invoice");
  const canManual = available.has("manual_invoice");
  const canMarkIncome = available.has("mark_income_status");
  const canViewRelation = available.has("view_relation");
  const menuItems: Array<{ key: string; label: string; onClick: () => void }> = [];

  if (action === "mark_income_status" && canMarkIncome) {
    menuItems.push(
      { key: "income_no_invoice_required", label: "无需开票", onClick: () => onMarkIncomeStatus(row, "income_no_invoice_required") },
      { key: "cash_income", label: "现金收入", onClick: () => onMarkIncomeStatus(row, "cash_income") },
    );
  }
  if (action === "attach_or_create_invoice" && (canAttach || canManual)) {
    if (canAttach) {
      menuItems.push({ key: "attach_existing_invoice", label: "选择发票", onClick: () => onOpenInvoicePicker(row) });
    }
    if (canManual) {
      menuItems.push({ key: "manual_invoice", label: "补票", onClick: () => onOpenManualInvoice(row) });
    }
  }
  if (shouldOpenRelation(action) && canViewRelation) {
    menuItems.push({ key: "view_relation", label: "查看支付明细", onClick: () => onOpenRelation(row) });
  }
  if (shouldOpenInvoicePicker(action) && canAttach) {
    menuItems.push({ key: "choose_invoice", label: "选择发票", onClick: () => onOpenInvoicePicker(row) });
  }
  if (shouldOpenManualInvoice(action) && canManual) {
    menuItems.push({ key: "create_invoice", label: "补票", onClick: () => onOpenManualInvoice(row) });
  }
  if (menuItems.length === 0) {
    return null;
  }

  return (
    <div
      className="pending-invoices-row-menu"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setOpen(false);
        }
      }}
    >
      <button
        aria-expanded={open ? "true" : undefined}
        aria-haspopup="menu"
        aria-label={`${prefix} 发票获取操作`}
        className="pending-invoices-row-menu-trigger"
        onClick={() => setOpen((current) => !current)}
        title="发票获取操作"
        type="button"
      >
        <MoreVertical aria-hidden="true" size={15} strokeWidth={2.4} />
      </button>
      {open ? (
        <div aria-label={`${prefix} 发票获取操作菜单`} className="pending-invoices-row-menu-content" role="menu">
          {menuItems.map((item) => (
            <button
              className="pending-invoices-row-menu-item"
              disabled={disabled}
              key={item.key}
              onClick={() => {
                setOpen(false);
                item.onClick();
              }}
              role="menuitem"
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function PendingInvoicesTable({
  rows,
  config,
  onSortChange,
  onOpenRelation,
  onOpenInvoicePicker,
  onOpenManualInvoice,
  onOpenObjectDetail,
  onMarkIncomeStatus,
  direction,
  statusFilterControl,
  filterFields,
  columnFilters,
  onApplyColumnFilters,
  onClearColumnFilters,
  pendingActionRowIds,
  selectedTransactionIds,
  onToggleTransactionSelection,
  isTransactionSelectable,
  tableWrapRef,
}: PendingInvoicesTableProps) {
  const bankGroupLabel = direction === "income" ? "收入流水" : direction === "all" ? "流水" : "支出流水";
  const invoiceGroupLabel = direction === "income" ? "销项发票" : direction === "all" ? "发票" : "进项发票";
  const invoicePartyLabel = direction === "income" ? "购方 / 识别号" : "供应商 / 识别号";
  const counterpartyFilter: ColumnFilterGroup = {
    label: "对方户名 / 时间",
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
  const sortDescriptor = useMemo<SortDescriptor>(() => ({
    column: config.sortField,
    direction: config.sortDirection === "asc" ? "ascending" : "descending",
  }), [config.sortDirection, config.sortField]);

  function handleHeroSortChange(descriptor: SortDescriptor) {
    if (!isPendingInvoiceSortField(descriptor.column)) {
      return;
    }
    onSortChange(descriptor.column, descriptor.direction === "ascending" ? "asc" : "desc");
  }

  return (
    <div className="pending-invoices-table-frame">
      <div aria-hidden="true" className="pending-invoices-table-zone-header-grid">
        <div className="pending-invoices-table-group-header pending-invoices-table-group-header--bank">{bankGroupLabel}</div>
        <div className="pending-invoices-table-group-header pending-invoices-table-group-header--status pending-invoices-table-cell--left-border">发票获取状态</div>
        <div className="pending-invoices-table-group-header pending-invoices-table-group-header--invoice pending-invoices-table-cell--left-border">{invoiceGroupLabel}</div>
        <div className="pending-invoices-table-group-header pending-invoices-table-group-header--oa pending-invoices-table-cell--left-border">OA</div>
      </div>
      <Table variant="secondary">
        <Table.ScrollContainer ref={tableWrapRef} className="pending-invoices-table-shell" data-testid="pending-invoices-table-shell">
          <Table.Content
            aria-label="待找发票四区表"
            className="pending-invoices-table"
            sortDescriptor={sortDescriptor}
            onSortChange={handleHeroSortChange}
          >
            <Table.Header>
              <Table.Column allowsSorting isRowHeader aria-label="对方户名 / 时间" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-col-counterparty" id="counterparty_name">
                {({ sortDirection }) => sortableHeader({
                  label: "对方户名 / 时间",
                  sortDirection,
                  filterMenu: <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={counterpartyFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />,
                })}
              </Table.Column>
              <Table.Column allowsSorting aria-label="金额 / 银行账户" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-table-cell--amount pending-invoices-col-amount" id="amount">
                {({ sortDirection }) => sortableHeader({
                  label: "金额 / 银行账户",
                  sortDirection,
                  filterMenu: <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={amountFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />,
                })}
              </Table.Column>
              <Table.Column aria-label="摘要 / 凭证" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-col-summary" id="summary">摘要 / 凭证</Table.Column>
              <Table.Column aria-label="全部" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--status pending-invoices-table-cell--left-border pending-invoices-col-status" id="invoice_status">
                <div className="pending-invoices-status-filter-cell">{statusFilterControl}</div>
              </Table.Column>
              <Table.Column allowsSorting aria-label="发票号码 / 开票日期" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-table-cell--left-border pending-invoices-col-invoice-no" id="trade_date">
                {({ sortDirection }) => sortableHeader({ label: "发票号码 / 开票日期", sortDirection })}
              </Table.Column>
              <Table.Column allowsSorting aria-label={invoicePartyLabel} className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-col-seller" id="seller_name">
                {({ sortDirection }) => sortableHeader({
                  label: invoicePartyLabel,
                  sortDirection,
                  filterMenu: <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={invoicePartyFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />,
                })}
              </Table.Column>
              <Table.Column allowsSorting aria-label="金额 / 支付差额" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-table-cell--amount pending-invoices-col-invoice-amount" id="invoice_total">
                {({ sortDirection }) => sortableHeader({ label: "金额 / 支付差额", sortDirection })}
              </Table.Column>
              <Table.Column allowsSorting aria-label="申请人 / 类型" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--oa pending-invoices-table-cell--left-border pending-invoices-col-oa-applicant" id="oa_applicant">
                {({ sortDirection }) => sortableHeader({
                  label: "申请人 / 类型",
                  sortDirection,
                  filterMenu: <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={oaFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />,
                })}
              </Table.Column>
              <Table.Column allowsSorting aria-label="项目" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--oa pending-invoices-col-oa-project" id="project_name">
                {({ sortDirection }) => sortableHeader({
                  label: "项目",
                  sortDirection,
                  filterMenu: <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={projectFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />,
                })}
              </Table.Column>
            </Table.Header>
            <Table.Body>
              {rows.length === 0 ? (
                <Table.Row id="pending-invoices-empty" textValue="当前条件下没有待找发票流水">
                  <Table.Cell className="pending-invoices-table-state-cell" colSpan={9}>
                    当前条件下没有待找发票流水。
                  </Table.Cell>
                </Table.Row>
              ) : rows.map((row) => (
                <PendingInvoiceTableRow
                  actionPending={pendingActionRowIds?.has(row.id) ?? false}
                  direction={direction}
                  key={row.id}
                  onMarkIncomeStatus={onMarkIncomeStatus}
                  onOpenInvoicePicker={onOpenInvoicePicker}
                  onOpenManualInvoice={onOpenManualInvoice}
                  onOpenObjectDetail={onOpenObjectDetail}
                  onOpenRelation={onOpenRelation}
                  onToggleTransactionSelection={onToggleTransactionSelection}
                  row={row}
                  selectedTransactionIds={selectedTransactionIds}
                  isTransactionSelectable={isTransactionSelectable}
                />
              ))}
            </Table.Body>
          </Table.Content>
        </Table.ScrollContainer>
      </Table>
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
  row,
  direction,
  onOpenRelation,
  onOpenInvoicePicker,
  onOpenManualInvoice,
  onOpenObjectDetail,
  onMarkIncomeStatus,
  selectedTransactionIds,
  onToggleTransactionSelection,
  isTransactionSelectable,
  actionPending = false,
}: Omit<PendingInvoicesTableProps, "rows" | "config" | "onSortChange" | "statusFilterControl" | "filterFields" | "columnFilters" | "onApplyColumnFilters" | "onClearColumnFilters" | "pendingActionRowIds"> & { row: PendingInvoiceRow; actionPending?: boolean }) {
  const primaryInvoice = row.inputInvoices.primary;
  const primaryOa = row.oa.primary;
  const invoiceExtraCount = Math.max(0, row.inputInvoices.relationCount - 1);
  const oaExtraCount = Math.max(0, row.oa.relationCount - 1);
  const oaDetailAvailable = canOpenOaDetail(row);
  const moneyDirection = rowMoneyDirection(row, direction);
  const invoiceNumberLabel = primaryInvoice ? invoiceNumber(primaryInvoice) : "";
  const transactionId = row.bankTransaction.id || row.id;
  const transactionSelectable = isTransactionSelectable?.(row) === true;
  const transactionSelected = selectedTransactionIds?.has(transactionId) === true;
  const invoiceTotal = row.inputInvoices.paymentSummary?.invoiceTotal || primaryInvoice?.totalWithTax || "";

  return (
    <Table.Row className="pending-invoices-table-row" id={row.id} textValue={row.bankTransaction.counterpartyName || row.id}>
      <Table.Cell className="pending-invoices-table-cell pending-invoices-col-counterparty" data-column-role="identity">
        <span className="pending-invoices-counterparty-cell pending-invoices-counterparty-cell--selectable">
          <span className="pending-invoices-row-select-slot">
            {transactionSelectable ? (
              <input
                aria-label={`选择流水 ${row.bankTransaction.counterpartyName || row.id}`}
                checked={transactionSelected}
                className="pending-invoices-row-select"
                onChange={() => onToggleTransactionSelection?.(row)}
                type="checkbox"
              />
            ) : null}
          </span>
          <span className="pending-invoices-counterparty-content">
            <span className="pending-invoices-counterparty-row">
              <span className="pending-invoices-counterparty-name" title={row.bankTransaction.counterpartyName}>
                {row.bankTransaction.counterpartyName}
              </span>
              <button
                aria-label={`流水详情 ${row.bankTransaction.counterpartyName}`}
                className="pending-invoices-icon-button"
                onClick={() => onOpenObjectDetail({ kind: "bankTransaction", id: row.bankTransaction.id, rowId: row.id })}
                title="流水详情"
                type="button"
              >
                <Info aria-hidden="true" size={14} strokeWidth={2.3} />
              </button>
            </span>
            <span className="pending-invoices-cell-secondary">{row.bankTransaction.tradeTime || "-"}</span>
            <span className="pending-invoices-tag pending-invoices-tag--neutral" title={tagPathLabel(row.bankTransaction)}>
              {tagPathLabel(row.bankTransaction)}
            </span>
          </span>
        </span>
      </Table.Cell>
      <Table.Cell className="pending-invoices-table-cell pending-invoices-table-cell--amount pending-invoices-col-amount" data-column-role="amount">
        <AmountCell
          account={bankAccountLabel(row.bankTransaction)}
          amount={formatMoney(row.bankTransaction.amount)}
          className="pending-invoices-amount-cell"
          direction={<FinanceDirectionTag direction={moneyDirection}>{moneyDirection === "income" ? "收" : "支"}</FinanceDirectionTag>}
        />
      </Table.Cell>
      <Table.Cell className="pending-invoices-table-cell pending-invoices-table-cell--summary pending-invoices-col-summary" data-column-role="description">
        <TextCell
          primary={row.bankTransaction.summary || <EmptyValue />}
          secondary={row.bankTransaction.remark || row.bankTransaction.voucherNo || <EmptyValue />}
          title={row.bankTransaction.summary}
        />
      </Table.Cell>
      <Table.Cell className="pending-invoices-table-cell pending-invoices-table-cell--status pending-invoices-table-cell--left-border pending-invoices-col-status" data-column-role="status">
        <span className="pending-invoices-status-cell">
          <span aria-hidden="true" />
          <FinanceStatusTag tone={severityTone(row.invoiceAcquisitionStatus.severity)}>
            {row.invoiceAcquisitionStatus.label}
          </FinanceStatusTag>
          <RowActionMenu
            disabled={actionPending}
            onMarkIncomeStatus={onMarkIncomeStatus}
            onOpenInvoicePicker={onOpenInvoicePicker}
            onOpenManualInvoice={onOpenManualInvoice}
            onOpenRelation={onOpenRelation}
            row={row}
          />
        </span>
      </Table.Cell>
      <Table.Cell className="pending-invoices-table-cell pending-invoices-table-cell--left-border pending-invoices-col-invoice-no" data-column-role="identity">
        {primaryInvoice ? (
          <TextCell
            primary={invoiceNumberLabel}
            secondary={(
              <span className="pending-invoices-inline-row">
                <span>{primaryInvoice.issueDate || "-"}</span>
                <DetailButton
                  label={`发票详情 ${invoiceNumberLabel}`}
                  onClick={() => onOpenObjectDetail({ kind: "invoice", id: primaryInvoice.id, rowId: row.id })}
                >
                  <Info aria-hidden="true" size={14} strokeWidth={2.3} />
                </DetailButton>
                {invoiceExtraCount > 0 ? (
                  <DetailButton label={`${row.bankTransaction.counterpartyName} 查看全部发票关系`} onClick={() => onOpenRelation(row)}>
                    +{invoiceExtraCount}
                  </DetailButton>
                ) : null}
              </span>
            )}
            title={invoiceNumberLabel}
          />
        ) : <EmptyValue />}
      </Table.Cell>
      <Table.Cell className="pending-invoices-table-cell pending-invoices-col-seller" data-column-role="identity">
        {primaryInvoice ? (
          <TextCell
            primary={primaryInvoice.sellerName || <EmptyValue />}
            secondary={primaryInvoice.sellerTaxNo || <EmptyValue />}
            title={primaryInvoice.sellerName}
          />
        ) : <EmptyValue />}
      </Table.Cell>
      <Table.Cell className="pending-invoices-table-cell pending-invoices-table-cell--amount pending-invoices-col-invoice-amount" data-column-role="amount">
        {primaryInvoice ? (
          <span className="pending-invoices-money-stack">
            <span className="pending-invoices-money-primary">
              {formatMoney(invoiceTotal)}
              {invoiceExtraCount > 0 ? <span className="pending-invoices-money-extra"> +{invoiceExtraCount}</span> : null}
            </span>
            {row.inputInvoices.paymentSummary ? (
              <>
                <span className="pending-invoices-cell-secondary">已付 {formatMoney(row.inputInvoices.paymentSummary.paidTotal)}</span>
                <span className="pending-invoices-cell-secondary">待付 {formatMoney(row.inputInvoices.paymentSummary.remainingAmount)}</span>
              </>
            ) : null}
          </span>
        ) : <EmptyValue />}
      </Table.Cell>
      <Table.Cell className="pending-invoices-table-cell pending-invoices-table-cell--left-border pending-invoices-col-oa-applicant" data-column-role="identity">
        {primaryOa ? (
          <TextCell
            primary={primaryOa.applicant || <EmptyValue />}
            secondary={primaryOa.applicationType || <EmptyValue />}
            title={primaryOa.applicant}
          />
        ) : <EmptyValue />}
      </Table.Cell>
      <Table.Cell className="pending-invoices-table-cell pending-invoices-col-oa-project" data-column-role="description">
        {primaryOa ? (
          <TextCell
            primary={primaryOa.projectName || <EmptyValue />}
            secondary={(
              <span className="pending-invoices-inline-row">
                <DetailButton
                  disabled={!oaDetailAvailable}
                  label={`OA详情 ${primaryOa.applicant || primaryOa.id}`}
                  onClick={() => onOpenObjectDetail({ kind: "oa", id: primaryOa.id, rowId: row.id })}
                >
                  <Info aria-hidden="true" size={14} strokeWidth={2.3} />
                </DetailButton>
                {oaExtraCount > 0 ? (
                  <DetailButton label={`${row.bankTransaction.counterpartyName} 查看全部 OA 关系`} onClick={() => onOpenRelation(row)}>
                    +{oaExtraCount}
                  </DetailButton>
                ) : null}
              </span>
            )}
            title={primaryOa.projectName}
          />
        ) : <EmptyValue />}
      </Table.Cell>
    </Table.Row>
  );
}

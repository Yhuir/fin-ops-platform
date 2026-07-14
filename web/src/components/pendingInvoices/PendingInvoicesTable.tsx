import { Button, Dropdown, Label, Table, type Selection } from "@heroui/react";
import { Filter, Info } from "lucide-react";
import { useState, type MutableRefObject, type ReactNode } from "react";

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
  PendingInvoiceRelationDetailKind,
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
  onOpenRelation: (row: PendingInvoiceRow, kind?: PendingInvoiceRelationDetailKind) => void;
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

function uniqueCounterpartyLabel(row: PendingInvoiceRow) {
  const seen = new Set<string>();
  const names = row.bankTransactions.summaries
    .map((item) => item.counterpartyName.trim())
    .filter((name) => {
      if (!name || seen.has(name)) {
        return false;
      }
      seen.add(name);
      return true;
    });
  return names.join("、") || row.bankTransaction.counterpartyName || "-";
}

function RelationStatusChip({ status }: { status?: string }) {
  if (!status) {
    return null;
  }
  const paired = status.trim().toLowerCase() === "linked";
  return (
    <span className={`pending-invoices-tag pending-invoices-tag--${paired ? "linked" : "unlinked"}`}>
      {paired ? "已配对" : "未配对"}
    </span>
  );
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

function canOpenOaDetail(row: PendingInvoiceRow) {
  const primaryOa = row.oa.primary;
  return Boolean(primaryOa?.id?.startsWith("oa-") && primaryOa.detailAvailable && row.oa.detailAvailable);
}

export default function PendingInvoicesTable({
  rows,
  config,
  onSortChange,
  onOpenRelation,
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
}: PendingInvoicesTableProps) {
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

  function ariaSortFor(field: PendingInvoiceSortField) {
    return sortDirectionFor(field) ?? "none";
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
    <div className="pending-invoices-table-frame">
      <Table variant="secondary">
        <Table.ScrollContainer ref={tableWrapRef} className="pending-invoices-table-shell" data-testid="pending-invoices-table-shell">
          <div aria-hidden="true" className="pending-invoices-table-zone-header-grid">
            <div className="pending-invoices-table-group-header pending-invoices-table-group-header--bank">{bankGroupLabel}</div>
            <div className="pending-invoices-table-group-header pending-invoices-table-group-header--status pending-invoices-table-cell--left-border">发票获取状态</div>
            <div className="pending-invoices-table-group-header pending-invoices-table-group-header--invoice pending-invoices-table-cell--left-border">{invoiceGroupLabel}</div>
            <div className="pending-invoices-table-group-header pending-invoices-table-group-header--oa pending-invoices-table-cell--left-border">OA</div>
          </div>
          <table
            aria-label="待找发票四区表"
            className="pending-invoices-table"
            role="grid"
          >
            <colgroup>
              <col className="pending-invoices-col-counterparty" />
              <col className="pending-invoices-col-amount" />
              <col className="pending-invoices-col-summary" />
              <col className="pending-invoices-col-status" />
              <col className="pending-invoices-col-invoice-no" />
              <col className="pending-invoices-col-seller" />
              <col className="pending-invoices-col-invoice-amount" />
              <col className="pending-invoices-col-oa-applicant" />
              <col className="pending-invoices-col-oa-project" />
            </colgroup>
            <thead>
              <tr>
                <th aria-label="对方户名" aria-sort={ariaSortFor("counterparty_name")} className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-col-counterparty" id="counterparty_name" scope="col">
                  {renderSortableHeader("counterparty_name", "对方户名", <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={counterpartyFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </th>
                <th aria-label="金额 / 银行账户" aria-sort={ariaSortFor("amount")} className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-table-cell--amount pending-invoices-col-amount" id="amount" scope="col">
                  {renderSortableHeader("amount", "金额 / 银行账户", <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={amountFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </th>
                <th aria-label="摘要 / 凭证" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-col-summary" id="summary" scope="col">摘要 / 凭证</th>
                <th aria-label="全部" className="pending-invoices-table-sub-header pending-invoices-table-sub-header--status pending-invoices-table-cell--left-border pending-invoices-col-status" id="invoice_status" scope="col">
                  <div className="pending-invoices-status-filter-cell">{statusFilterControl}</div>
                </th>
                <th aria-label="发票号码 / 开票日期" aria-sort={ariaSortFor("trade_date")} className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-table-cell--left-border pending-invoices-col-invoice-no" id="trade_date" scope="col">
                  {renderSortableHeader("trade_date", "发票号码 / 开票日期")}
                </th>
                <th aria-label={invoicePartyLabel} aria-sort={ariaSortFor("seller_name")} className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-col-seller" id="seller_name" scope="col">
                  {renderSortableHeader("seller_name", invoicePartyLabel, <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={invoicePartyFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </th>
                <th aria-label="金额 / 支付差额" aria-sort={ariaSortFor("invoice_total")} className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-table-cell--amount pending-invoices-col-invoice-amount" id="invoice_total" scope="col">
                  {renderSortableHeader("invoice_total", "金额 / 支付差额")}
                </th>
                <th aria-label="申请人 / 类型" aria-sort={ariaSortFor("oa_applicant")} className="pending-invoices-table-sub-header pending-invoices-table-sub-header--oa pending-invoices-table-cell--left-border pending-invoices-col-oa-applicant" id="oa_applicant" scope="col">
                  {renderSortableHeader("oa_applicant", "申请人 / 类型", <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={oaFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </th>
                <th aria-label="项目" aria-sort={ariaSortFor("project_name")} className="pending-invoices-table-sub-header pending-invoices-table-sub-header--oa pending-invoices-col-oa-project" id="project_name" scope="col">
                  {renderSortableHeader("project_name", "项目", <ColumnFilterMenu columnFilters={columnFilters} filterFields={filterFields} group={projectFilter} onApply={onApplyColumnFilters} onClear={onClearColumnFilters} />)}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr id="pending-invoices-empty">
                  <td className="pending-invoices-table-state-cell" colSpan={9}>
                    {emptyStateMessage}
                  </td>
                </tr>
              ) : rows.map((row) => (
                <PendingInvoiceTableRow
                  direction={direction}
                  key={row.id}
                  onOpenObjectDetail={onOpenObjectDetail}
                  onOpenRelation={onOpenRelation}
                  onToggleTransactionSelection={onToggleTransactionSelection}
                  row={row}
                  selectedTransactionIds={selectedTransactionIds}
                  isTransactionSelectable={isTransactionSelectable}
                />
              ))}
            </tbody>
          </table>
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
  onOpenObjectDetail,
  selectedTransactionIds,
  onToggleTransactionSelection,
  isTransactionSelectable,
}: Omit<PendingInvoicesTableProps, "rows" | "config" | "onSortChange" | "statusFilterControl" | "filterFields" | "columnFilters" | "onApplyColumnFilters" | "onClearColumnFilters"> & { row: PendingInvoiceRow }) {
  const primaryInvoice = row.inputInvoices.primary;
  const primaryOa = row.oa.primary;
  const bankRelationCount = Math.max(0, row.bankTransactions.relationCount);
  const bankHasMultiple = row.bankTransactions.hasMultiple && bankRelationCount > 1;
  const invoiceRelationCount = Math.max(0, row.inputInvoices.relationCount);
  const invoiceHasMultiple = row.inputInvoices.hasMultiple && invoiceRelationCount > 1;
  const oaRelationCount = Math.max(0, row.oa.relationCount);
  const oaHasMultiple = row.oa.hasMultiple && oaRelationCount > 1;
  const oaDetailAvailable = canOpenOaDetail(row);
  const moneyDirection = rowMoneyDirection(row, direction);
  const invoiceNumberLabel = primaryInvoice ? invoiceNumber(primaryInvoice) : "";
  const transactionId = row.bankTransaction.id || row.id;
  const transactionSelectable = isTransactionSelectable?.(row) === true;
  const transactionSelected = selectedTransactionIds?.has(transactionId) === true;
  const invoiceTotal = row.inputInvoices.paymentSummary?.invoiceTotal || primaryInvoice?.totalWithTax || "";
  const bankTotal = bankHasMultiple
    ? row.bankTransactions.paymentSummary?.paidTotal || row.bankTransaction.amount
    : row.bankTransaction.amount;
  const counterpartyLabel = bankHasMultiple ? uniqueCounterpartyLabel(row) : row.bankTransaction.counterpartyName;

  return (
    <tr className="pending-invoices-table-row" id={row.id}>
      <td className="pending-invoices-table-cell pending-invoices-col-counterparty" data-column-role="identity" role="rowheader">
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
            {bankHasMultiple ? (
              <span className="pending-invoices-counterparty-row">
                <span className="pending-invoices-counterparty-name" title={counterpartyLabel}>
                  {counterpartyLabel}
                </span>
                <button
                  aria-label={`查看全部流水关系 ${counterpartyLabel}`}
                  className="pending-invoices-icon-button"
                  onClick={() => onOpenRelation(row, "bank")}
                  title="全部流水详情"
                  type="button"
                >
                  <Info aria-hidden="true" size={14} strokeWidth={2.3} />
                </button>
              </span>
            ) : (
              <>
                <span className="pending-invoices-counterparty-row">
                  <span className="pending-invoices-counterparty-name" title={counterpartyLabel}>
                    {counterpartyLabel}
                  </span>
                  <button
                    aria-label={`流水详情 ${counterpartyLabel}`}
                    className="pending-invoices-icon-button"
                    onClick={() => onOpenObjectDetail({ kind: "bankTransaction", id: row.bankTransaction.id, rowId: row.id })}
                    title="流水详情"
                    type="button"
                  >
                    <Info aria-hidden="true" size={14} strokeWidth={2.3} />
                  </button>
                </span>
                <span className="pending-invoices-tag pending-invoices-tag--neutral" title={tagPathLabel(row.bankTransaction)}>
                  {tagPathLabel(row.bankTransaction)}
                </span>
              </>
            )}
          </span>
        </span>
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--amount pending-invoices-col-amount" data-column-role="amount" role="gridcell">
        <AmountCell
          account={bankHasMultiple ? `${bankRelationCount} 笔流水` : bankAccountLabel(row.bankTransaction)}
          amount={formatMoney(bankTotal)}
          className="pending-invoices-amount-cell"
          direction={<FinanceDirectionTag direction={moneyDirection}>{moneyDirection === "income" ? "收" : "支"}</FinanceDirectionTag>}
        />
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--summary pending-invoices-col-summary" data-column-role="description" role="gridcell">
        {bankHasMultiple ? <EmptyValue /> : (
          <TextCell
            primary={row.bankTransaction.summary || <EmptyValue />}
            secondary={row.bankTransaction.remark || row.bankTransaction.voucherNo || <EmptyValue />}
            title={row.bankTransaction.summary}
          />
        )}
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--status pending-invoices-table-cell--left-border pending-invoices-col-status" data-column-role="status" role="gridcell">
        <span className="pending-invoices-status-cell">
          <FinanceStatusTag tone={severityTone(row.invoiceAcquisitionStatus.severity)}>
            {row.invoiceAcquisitionStatus.label}
          </FinanceStatusTag>
        </span>
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--left-border pending-invoices-col-invoice-no" data-column-role="identity" role="gridcell">
        {invoiceHasMultiple ? (
          <DetailButton label="查看全部发票关系" onClick={() => onOpenRelation(row, "invoice")}>
            +{invoiceRelationCount}
          </DetailButton>
        ) : primaryInvoice ? (
          <TextCell
            primary={invoiceNumberLabel}
            secondary={(
              <span className="pending-invoices-inline-row">
                <span>{primaryInvoice.issueDate || "-"}</span>
                <RelationStatusChip status={primaryInvoice.relationStatus} />
                <DetailButton
                  label={`发票详情 ${invoiceNumberLabel}`}
                  onClick={() => onOpenObjectDetail({ kind: "invoice", id: primaryInvoice.id, rowId: row.id })}
                >
                  <Info aria-hidden="true" size={14} strokeWidth={2.3} />
                </DetailButton>
              </span>
            )}
            title={invoiceNumberLabel}
          />
        ) : <EmptyValue />}
      </td>
      <td className="pending-invoices-table-cell pending-invoices-col-seller" data-column-role="identity" role="gridcell">
        {!invoiceHasMultiple && primaryInvoice ? (
          <TextCell
            primary={primaryInvoice.sellerName || <EmptyValue />}
            secondary={primaryInvoice.sellerTaxNo || <EmptyValue />}
            title={primaryInvoice.sellerName}
          />
        ) : <EmptyValue />}
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--amount pending-invoices-col-invoice-amount" data-column-role="amount" role="gridcell">
        {primaryInvoice || invoiceHasMultiple ? (
          <span className="pending-invoices-money-stack">
            <span className="pending-invoices-money-primary">
              {formatMoney(invoiceTotal)}
            </span>
            {row.inputInvoices.paymentSummary ? (
              <>
                <span className="pending-invoices-cell-secondary">已付 {formatMoney(row.inputInvoices.paymentSummary.paidTotal)}</span>
                <span className="pending-invoices-cell-secondary">待付 {formatMoney(row.inputInvoices.paymentSummary.remainingAmount)}</span>
              </>
            ) : null}
          </span>
        ) : <EmptyValue />}
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--left-border pending-invoices-col-oa-applicant" data-column-role="identity" role="gridcell">
        {oaHasMultiple ? (
          <DetailButton label="查看全部 OA 关系" onClick={() => onOpenRelation(row, "oa")}>
            +{oaRelationCount}
          </DetailButton>
        ) : primaryOa ? (
          <TextCell
            primary={primaryOa.applicant || <EmptyValue />}
            secondary={(
              <span className="pending-invoices-inline-row">
                <span>{primaryOa.applicationType || <EmptyValue />}</span>
                <RelationStatusChip status={primaryOa.relationStatus} />
              </span>
            )}
            title={primaryOa.applicant}
          />
        ) : <EmptyValue />}
      </td>
      <td className="pending-invoices-table-cell pending-invoices-col-oa-project" data-column-role="description" role="gridcell">
        {!oaHasMultiple && primaryOa ? (
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
              </span>
            )}
            title={primaryOa.projectName}
          />
        ) : <EmptyValue />}
      </td>
    </tr>
  );
}

import { Info, MoreVertical } from "lucide-react";
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
  onSortChange: (field: PendingInvoiceSortField) => void;
  onOpenRelation: (row: PendingInvoiceRow) => void;
  onOpenInvoicePicker: (row: PendingInvoiceRow) => void;
  onOpenManualInvoice: (row: PendingInvoiceRow) => void;
  onOpenObjectDetail: (target: PendingInvoiceObjectDetailTarget) => void;
  onMarkIncomeStatus: (row: PendingInvoiceRow, statusCode: "income_no_invoice_required" | "cash_income") => void;
  direction: PendingInvoiceDirection;
  statusFilterControl: ReactNode;
  pendingActionRowIds?: Set<string>;
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

function SortButton({
  label,
  field,
  config,
  onSortChange,
}: {
  label: string;
  field: PendingInvoiceSortField;
  config: PendingInvoicesTableConfig;
  onSortChange: (field: PendingInvoiceSortField) => void;
}) {
  const active = config.sortField === field;
  const direction = active ? config.sortDirection : "asc";
  return (
    <button
      className="pending-invoices-sort-button"
      data-sort-direction={active ? direction : undefined}
      onClick={() => onSortChange(field)}
      type="button"
    >
      <span>{label}</span>
      <span aria-hidden="true" className="pending-invoices-sort-icon">{active ? (direction === "asc" ? "↑" : "↓") : "↕"}</span>
    </button>
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
  pendingActionRowIds,
  tableWrapRef,
}: PendingInvoicesTableProps) {
  const bankGroupLabel = direction === "income" ? "收入流水" : direction === "all" ? "流水" : "支出流水";
  const invoiceGroupLabel = direction === "income" ? "销项发票" : direction === "all" ? "发票" : "进项发票";
  return (
    <div className="pending-invoices-table-frame">
      <div ref={tableWrapRef} className="pending-invoices-table-shell" data-testid="pending-invoices-table-shell">
        <table aria-label="待找发票四区表" className="pending-invoices-table">
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
              <th className="pending-invoices-table-group-header pending-invoices-table-group-header--bank" colSpan={3} scope="colgroup">{bankGroupLabel}</th>
              <th className="pending-invoices-table-group-header pending-invoices-table-group-header--status pending-invoices-table-cell--left-border" scope="colgroup">发票获取状态</th>
              <th className="pending-invoices-table-group-header pending-invoices-table-group-header--invoice pending-invoices-table-cell--left-border" colSpan={3} scope="colgroup">{invoiceGroupLabel}</th>
              <th className="pending-invoices-table-group-header pending-invoices-table-group-header--oa pending-invoices-table-cell--left-border" colSpan={2} scope="colgroup">OA</th>
            </tr>
            <tr>
              <th className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank" scope="col">
                <SortButton config={config} field="counterparty_name" label="对方 / 时间" onSortChange={onSortChange} />
              </th>
              <th className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank pending-invoices-table-cell--amount" scope="col">
                <SortButton config={config} field="amount" label="金额 / 银行账户" onSortChange={onSortChange} />
              </th>
              <th className="pending-invoices-table-sub-header pending-invoices-table-sub-header--bank" scope="col">摘要 / 凭证</th>
              <th className="pending-invoices-table-sub-header pending-invoices-table-sub-header--status pending-invoices-table-cell--left-border" scope="col">
                <div className="pending-invoices-status-filter-cell">{statusFilterControl}</div>
              </th>
              <th className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-table-cell--left-border" scope="col">
                <SortButton config={config} field="trade_date" label="发票号码 / 开票日期" onSortChange={onSortChange} />
              </th>
              <th className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice" scope="col">
                <SortButton config={config} field="seller_name" label="销方 / 识别号" onSortChange={onSortChange} />
              </th>
              <th className="pending-invoices-table-sub-header pending-invoices-table-sub-header--invoice pending-invoices-table-cell--amount" scope="col">
                <SortButton config={config} field="invoice_total" label="金额 / 支付差额" onSortChange={onSortChange} />
              </th>
              <th className="pending-invoices-table-sub-header pending-invoices-table-sub-header--oa pending-invoices-table-cell--left-border" scope="col">
                <SortButton config={config} field="oa_applicant" label="申请人 / 类型" onSortChange={onSortChange} />
              </th>
              <th className="pending-invoices-table-sub-header pending-invoices-table-sub-header--oa" scope="col">
                <SortButton config={config} field="project_name" label="项目 / 详情" onSortChange={onSortChange} />
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="pending-invoices-table-state-cell" colSpan={9}>
                  当前条件下没有待找发票流水。
                </td>
              </tr>
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
                row={row}
              />
            ))}
          </tbody>
        </table>
      </div>
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
  actionPending = false,
}: Omit<PendingInvoicesTableProps, "rows" | "config" | "onSortChange" | "statusFilterControl" | "pendingActionRowIds"> & { row: PendingInvoiceRow; actionPending?: boolean }) {
  const primaryInvoice = row.inputInvoices.primary;
  const primaryOa = row.oa.primary;
  const invoiceExtraCount = Math.max(0, row.inputInvoices.relationCount - 1);
  const oaExtraCount = Math.max(0, row.oa.relationCount - 1);
  const oaDetailAvailable = canOpenOaDetail(row);
  const moneyDirection = rowMoneyDirection(row, direction);
  const invoiceNumberLabel = primaryInvoice ? invoiceNumber(primaryInvoice) : "";

  return (
    <tr className="pending-invoices-table-row">
      <td className="pending-invoices-table-cell" data-column-role="identity">
        <span className="pending-invoices-counterparty-cell">
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
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--amount" data-column-role="amount">
        <AmountCell
          account={bankAccountLabel(row.bankTransaction)}
          amount={formatMoney(row.bankTransaction.amount)}
          className="pending-invoices-amount-cell"
          direction={<FinanceDirectionTag direction={moneyDirection}>{moneyDirection === "income" ? "收" : "支"}</FinanceDirectionTag>}
        />
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--summary" data-column-role="description">
        <TextCell
          primary={row.bankTransaction.summary || <EmptyValue />}
          secondary={row.bankTransaction.remark || row.bankTransaction.voucherNo || <EmptyValue />}
          title={row.bankTransaction.summary}
        />
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--status pending-invoices-table-cell--left-border" data-column-role="status">
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
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--left-border" data-column-role="identity">
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
                  详情
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
      </td>
      <td className="pending-invoices-table-cell" data-column-role="identity">
        {primaryInvoice ? (
          <TextCell
            primary={primaryInvoice.sellerName || <EmptyValue />}
            secondary={primaryInvoice.sellerTaxNo || <EmptyValue />}
            title={primaryInvoice.sellerName}
          />
        ) : <EmptyValue />}
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--amount" data-column-role="amount">
        {primaryInvoice ? (
          <span className="pending-invoices-money-stack">
            <span className="pending-invoices-money-primary">{formatMoney(primaryInvoice.totalWithTax)}</span>
            {row.inputInvoices.paymentSummary ? (
              <>
                <span className="pending-invoices-cell-secondary">已付 {formatMoney(row.inputInvoices.paymentSummary.paidTotal)}</span>
                <span className="pending-invoices-cell-secondary">待付 {formatMoney(row.inputInvoices.paymentSummary.remainingAmount)}</span>
              </>
            ) : null}
          </span>
        ) : <EmptyValue />}
      </td>
      <td className="pending-invoices-table-cell pending-invoices-table-cell--left-border" data-column-role="identity">
        {primaryOa ? (
          <TextCell
            primary={primaryOa.applicant || <EmptyValue />}
            secondary={primaryOa.applicationType || <EmptyValue />}
            title={primaryOa.applicant}
          />
        ) : <EmptyValue />}
      </td>
      <td className="pending-invoices-table-cell" data-column-role="description">
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
                  详情
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
      </td>
    </tr>
  );
}
